"""Graph repository — DuckDB-backed storage for the knowledge graph.

Provides CRUD operations for nodes, edges, captures, and proposals,
with atomic transaction support for committing graph proposals.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import duckdb

from .models import (
    BaseNode,
    Capture,
    Edge,
    EdgeCategory,
    EdgeType,
    GraphProposal,
    NetworkType,
    NodeFilter,
    NodeType,
    ProposalRoute,
    ProposalStatus,
    Subgraph,
    NODE_TYPE_MODEL_MAP,
    parse_properties,
)

logger = logging.getLogger(__name__)

# Central "You" node — fixed UUID for the ego/user node
YOU_NODE_ID = "00000000-0000-0000-0000-000000000001"

# ============================================================
# Schema DDL
# ============================================================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS captures (
    id              VARCHAR PRIMARY KEY,
    modality        VARCHAR NOT NULL,
    raw_content     TEXT NOT NULL,
    processed_content TEXT,
    content_hash    VARCHAR(64) NOT NULL UNIQUE,
    language        VARCHAR(10),
    metadata        JSON,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nodes (
    id              VARCHAR PRIMARY KEY,
    node_type       VARCHAR NOT NULL,
    title           VARCHAR NOT NULL,
    content         TEXT,
    content_hash    VARCHAR(64) NOT NULL,
    properties      JSON,
    confidence      DOUBLE CHECK (confidence >= 0 AND confidence <= 1),
    networks        VARCHAR[],
    human_approved  BOOLEAN DEFAULT FALSE,
    proposed_by     VARCHAR,
    source_capture_id VARCHAR,
    access_count    INTEGER DEFAULT 0,
    last_accessed   TIMESTAMP,
    decay_score     DOUBLE DEFAULT 1.0,
    review_date     TIMESTAMP,
    tags            VARCHAR[],
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted         BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS edges (
    id              VARCHAR PRIMARY KEY,
    source_id       VARCHAR NOT NULL,
    target_id       VARCHAR NOT NULL,
    edge_type       VARCHAR NOT NULL,
    edge_category   VARCHAR NOT NULL,
    properties      JSON,
    confidence      DOUBLE CHECK (confidence >= 0 AND confidence <= 1),
    weight          DOUBLE DEFAULT 1.0,
    bidirectional   BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS proposals (
    id              VARCHAR PRIMARY KEY,
    capture_id      VARCHAR,
    agent_id        VARCHAR NOT NULL,
    status          VARCHAR DEFAULT 'pending',
    route           VARCHAR,
    confidence      DOUBLE,
    proposal_data   JSON NOT NULL,
    human_summary   TEXT,
    reviewed_at     TIMESTAMP,
    reviewer        VARCHAR,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS network_health (
    id              VARCHAR PRIMARY KEY,
    network         VARCHAR NOT NULL,
    status          VARCHAR NOT NULL,
    momentum        VARCHAR DEFAULT 'stable',
    commitment_completion_rate DOUBLE,
    alert_ratio     DOUBLE,
    staleness_flags INTEGER DEFAULT 0,
    computed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bridges (
    id              VARCHAR PRIMARY KEY,
    source_node_id  VARCHAR,
    target_node_id  VARCHAR,
    source_network  VARCHAR NOT NULL,
    target_network  VARCHAR NOT NULL,
    similarity      DOUBLE,
    llm_validated   BOOLEAN DEFAULT FALSE,
    meaningful      BOOLEAN,
    description     TEXT,
    discovered_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schema_version (
    version         INTEGER PRIMARY KEY,
    applied_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_records (
    id              VARCHAR PRIMARY KEY,
    connector_name  VARCHAR NOT NULL,
    connector_type  VARCHAR NOT NULL,
    last_sync       TIMESTAMP,
    items_synced    INTEGER DEFAULT 0,
    errors          INTEGER DEFAULT 0,
    cursor          VARCHAR,
    config          JSON,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


# ============================================================
# Repository
# ============================================================


class GraphRepository:
    """DuckDB-backed graph repository with CRUD and transaction support."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize repository.

        Args:
            db_path: Path to DuckDB file. None for in-memory database.
        """
        if db_path is None:
            self._conn = duckdb.connect(":memory:")
        else:
            db_path = Path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = duckdb.connect(str(db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables if they don't exist and run pending migrations."""
        from .migrations import apply_migrations

        for statement in SCHEMA_SQL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                self._conn.execute(stmt)
        # Record schema version
        count = self._conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        if count == 0:
            self._conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", [1]
            )
        # Apply any pending migrations
        apply_migrations(self._conn)

        # Ensure the central "You" node exists
        self._ensure_you_node()

    def _ensure_you_node(self) -> None:
        """Create the singleton PERSON node representing the user if absent."""
        row = self._conn.execute(
            "SELECT id FROM nodes WHERE id = ?", [YOU_NODE_ID]
        ).fetchone()
        if row is not None:
            return

        import hashlib

        now = datetime.now(UTC).isoformat()
        content = "Central node representing the user"
        content_hash = hashlib.sha256(f"You|{content}".encode()).hexdigest()

        self._conn.execute(
            """INSERT INTO nodes (id, node_type, title, content, content_hash,
               properties, confidence, networks, human_approved, proposed_by,
               source_capture_id, access_count, decay_score, tags,
               created_at, updated_at, deleted)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                YOU_NODE_ID,
                "PERSON",
                "You",
                content,
                content_hash,
                json.dumps({"name": "You", "relationship_to_user": "self"}),
                1.0,
                [],
                True,
                "system",
                None,
                0,
                1.0,
                [],
                now,
                now,
                False,
            ],
        )
        logger.info("Created central 'You' node: %s", YOU_NODE_ID)

    def get_you_node_id(self) -> str:
        """Return the fixed UUID of the central 'You' node."""
        return YOU_NODE_ID

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ---- Captures ----

    def create_capture(self, capture: Capture) -> UUID:
        """Insert a new capture. Returns the capture ID."""
        capture.compute_content_hash()
        self._conn.execute(
            """INSERT INTO captures (id, modality, raw_content, processed_content,
               content_hash, language, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                str(capture.id),
                capture.modality,
                capture.raw_content,
                capture.processed_content,
                capture.content_hash,
                capture.language,
                json.dumps(capture.metadata),
                capture.created_at.isoformat(),
            ],
        )
        return capture.id

    def get_capture(self, capture_id: UUID) -> Capture | None:
        """Retrieve a capture by ID."""
        row = self._conn.execute(
            "SELECT * FROM captures WHERE id = ?", [str(capture_id)]
        ).fetchone()
        if row is None:
            return None
        return self._row_to_capture(row)

    def list_captures(self, limit: int = 20, offset: int = 0) -> list[Capture]:
        """List captures ordered by most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM captures ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [limit, offset],
        ).fetchall()
        return [self._row_to_capture(row) for row in rows]

    def check_capture_exists(self, content_hash: str) -> bool:
        """Check if a capture with the given hash already has a successful proposal.

        A capture whose pipeline failed (no proposal created) should not block
        retries, so we only consider it a duplicate if a proposal exists for it.
        """
        result = self._conn.execute(
            """SELECT c.id FROM captures c
               WHERE c.content_hash = ?""",
            [content_hash],
        ).fetchone()
        if result is None:
            return False

        # Capture exists — check if it has an associated proposal
        capture_id = result[0]
        proposal = self._conn.execute(
            "SELECT COUNT(*) FROM proposals WHERE capture_id = ?", [capture_id]
        ).fetchone()
        if proposal[0] > 0:
            return True

        # Capture exists but no proposal — failed extraction. Delete the
        # stale capture so it can be re-ingested cleanly.
        self._conn.execute("DELETE FROM captures WHERE id = ?", [capture_id])
        return False

    # ---- Nodes ----

    def create_node(self, node: BaseNode) -> UUID:
        """Insert a new node. Returns the node ID."""
        node.compute_content_hash()
        self._conn.execute(
            """INSERT INTO nodes (id, node_type, title, content, content_hash,
               properties, confidence, networks, human_approved, proposed_by,
               source_capture_id, access_count, last_accessed, decay_score,
               review_date, tags, created_at, updated_at, deleted)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                str(node.id),
                node.node_type.value,
                node.title,
                node.content,
                node.content_hash,
                json.dumps(node.properties),
                node.confidence,
                [n.value for n in node.networks],
                node.human_approved,
                node.proposed_by,
                str(node.source_capture_id) if node.source_capture_id else None,
                node.access_count,
                node.last_accessed.isoformat() if node.last_accessed else None,
                node.decay_score,
                node.review_date.isoformat() if node.review_date else None,
                node.tags,
                node.created_at.isoformat(),
                node.updated_at.isoformat(),
                False,
            ],
        )
        return node.id

    def get_node(self, node_id: UUID) -> BaseNode | None:
        """Retrieve a node by ID (excludes soft-deleted)."""
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE id = ? AND deleted = FALSE", [str(node_id)]
        ).fetchone()
        if row is None:
            return None
        # Update access tracking
        self._conn.execute(
            "UPDATE nodes SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
            [datetime.now(UTC).isoformat(), str(node_id)],
        )
        return self._row_to_node(row)

    def get_nodes_batch(self, node_ids: list[str]) -> dict[str, BaseNode]:
        """Retrieve multiple nodes by ID in a single query (no access tracking)."""
        if not node_ids:
            return {}
        placeholders = ", ".join(["?"] * len(node_ids))
        rows = self._conn.execute(
            f"SELECT * FROM nodes WHERE id IN ({placeholders}) AND deleted = FALSE",
            node_ids,
        ).fetchall()
        result = {}
        for row in rows:
            node = self._row_to_node(row)
            result[str(node.id)] = node
        return result

    def get_connection_counts_batch(self, node_ids: list[str]) -> dict[str, int]:
        """Return {node_id: total_edge_count} for a batch of nodes."""
        if not node_ids:
            return {}
        placeholders = ", ".join(["?"] * len(node_ids))
        rows = self._conn.execute(
            f"""SELECT nid, SUM(cnt) FROM (
                    SELECT source_id AS nid, COUNT(*) AS cnt FROM edges
                    WHERE source_id IN ({placeholders}) GROUP BY source_id
                    UNION ALL
                    SELECT target_id AS nid, COUNT(*) AS cnt FROM edges
                    WHERE target_id IN ({placeholders}) GROUP BY target_id
                ) GROUP BY nid""",
            node_ids + node_ids,
        ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def get_edges_batch(self, node_ids: list[str]) -> list[Edge]:
        """Retrieve all edges connected to any of the given node IDs in a single query."""
        if not node_ids:
            return []
        placeholders = ", ".join(["?"] * len(node_ids))
        rows = self._conn.execute(
            f"SELECT * FROM edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
            node_ids + node_ids,
        ).fetchall()
        return [self._row_to_edge(row) for row in rows]

    def update_node(self, node_id: UUID, updates: dict[str, Any]) -> BaseNode | None:
        """Update specific fields of a node."""
        if not updates:
            return self.get_node(node_id)

        set_clauses = []
        params = []
        for key, value in updates.items():
            if key in ("id", "created_at"):
                continue
            if key == "properties":
                value = json.dumps(value)
            elif key == "networks":
                value = [n.value if isinstance(n, NetworkType) else n for n in value]
            elif key == "tags":
                pass  # already list
            elif isinstance(value, datetime):
                value = value.isoformat()
            elif isinstance(value, UUID):
                value = str(value)
            set_clauses.append(f"{key} = ?")
            params.append(value)

        set_clauses.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())
        params.append(str(node_id))

        self._conn.execute(
            f"UPDATE nodes SET {', '.join(set_clauses)} WHERE id = ? AND deleted = FALSE",
            params,
        )
        return self.get_node(node_id)

    def delete_node(self, node_id: UUID) -> bool:
        """Soft delete a node."""
        result = self._conn.execute(
            "UPDATE nodes SET deleted = TRUE, updated_at = ? WHERE id = ? AND deleted = FALSE",
            [datetime.now(UTC).isoformat(), str(node_id)],
        )
        return result.fetchone() is None  # DuckDB returns None for UPDATE

    def query_nodes(self, filters: NodeFilter) -> list[BaseNode]:
        """Query nodes with filters."""
        conditions = ["deleted = FALSE"]
        params: list[Any] = []

        if filters.node_types:
            placeholders = ", ".join(["?"] * len(filters.node_types))
            conditions.append(f"node_type IN ({placeholders})")
            params.extend(nt.value for nt in filters.node_types)

        if filters.networks:
            # Check if any of the filter networks overlap with the node's networks
            for net in filters.networks:
                conditions.append(f"list_contains(networks, ?)")
                params.append(net.value)

        if filters.tags:
            for tag in filters.tags:
                conditions.append(f"list_contains(tags, ?)")
                params.append(tag)

        if filters.min_confidence is not None:
            conditions.append("confidence >= ?")
            params.append(filters.min_confidence)

        if filters.min_decay_score is not None:
            conditions.append("decay_score >= ?")
            params.append(filters.min_decay_score)

        if filters.created_after is not None:
            conditions.append("created_at >= ?")
            params.append(filters.created_after.isoformat())

        if filters.created_before is not None:
            conditions.append("created_at <= ?")
            params.append(filters.created_before.isoformat())

        where = " AND ".join(conditions)
        query = f"SELECT * FROM nodes WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([filters.limit, filters.offset])

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_node(row) for row in rows]

    # ---- Edges ----

    def create_edge(self, edge: Edge) -> UUID:
        """Insert a new edge. Returns the edge ID."""
        self._conn.execute(
            """INSERT INTO edges (id, source_id, target_id, edge_type, edge_category,
               properties, confidence, weight, bidirectional, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                str(edge.id),
                str(edge.source_id),
                str(edge.target_id),
                edge.edge_type.value,
                edge.edge_category.value,
                json.dumps(edge.properties),
                edge.confidence,
                edge.weight,
                edge.bidirectional,
                edge.created_at.isoformat(),
                edge.updated_at.isoformat(),
            ],
        )
        return edge.id

    def update_edge_weight(self, edge_id: str, weight: float) -> None:
        """Update the weight of an edge."""
        self._conn.execute(
            "UPDATE edges SET weight = ?, updated_at = ? WHERE id = ?",
            [weight, datetime.now(UTC).isoformat(), edge_id],
        )

    def get_edges(self, node_id: UUID, direction: str = "both") -> list[Edge]:
        """Get edges connected to a node.

        Args:
            node_id: The node to query.
            direction: "outgoing", "incoming", or "both".
        """
        node_str = str(node_id)
        if direction == "outgoing":
            rows = self._conn.execute(
                "SELECT * FROM edges WHERE source_id = ?", [node_str]
            ).fetchall()
        elif direction == "incoming":
            rows = self._conn.execute(
                "SELECT * FROM edges WHERE target_id = ?", [node_str]
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM edges WHERE source_id = ? OR target_id = ?",
                [node_str, node_str],
            ).fetchall()
        return [self._row_to_edge(row) for row in rows]

    def get_neighborhood(self, node_id: UUID, hops: int = 1) -> Subgraph:
        """Get the subgraph within N hops of a node.

        Uses batch queries: one get_edges_batch per hop, then one get_nodes_batch
        for all discovered nodes.
        """
        visited_nodes: set[str] = set()
        frontier: set[str] = {str(node_id)}
        seen_edge_ids: set[str] = set()
        all_edges: list[Edge] = []

        for _ in range(hops):
            expand = [nid for nid in frontier if nid not in visited_nodes]
            if not expand:
                break
            visited_nodes.update(expand)
            edges = self.get_edges_batch(expand)

            next_frontier: set[str] = set()
            for edge in edges:
                eid = str(edge.id)
                if eid in seen_edge_ids:
                    continue
                seen_edge_ids.add(eid)
                all_edges.append(edge)
                src = str(edge.source_id)
                tgt = str(edge.target_id)
                if src not in visited_nodes:
                    next_frontier.add(src)
                if tgt not in visited_nodes:
                    next_frontier.add(tgt)
            frontier = next_frontier

        # Include last frontier nodes
        visited_nodes.update(frontier)

        # Single batch fetch for all nodes (no access tracking)
        nodes_map = self.get_nodes_batch(list(visited_nodes))
        nodes = list(nodes_map.values())

        return Subgraph(nodes=nodes, edges=all_edges)

    # ---- Proposals ----

    def create_proposal(
        self,
        proposal: GraphProposal,
        agent_id: str = "archivist",
        route: ProposalRoute = ProposalRoute.AUTO,
    ) -> UUID:
        """Store a graph proposal for review/commit."""
        proposal_id = uuid4()
        self._conn.execute(
            """INSERT INTO proposals (id, capture_id, agent_id, status, route,
               confidence, proposal_data, human_summary, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                str(proposal_id),
                proposal.source_capture_id,
                agent_id,
                ProposalStatus.PENDING.value,
                route.value,
                proposal.confidence,
                json.dumps(proposal.model_dump(mode="json")),
                proposal.human_summary,
                datetime.now(UTC).isoformat(),
            ],
        )
        return proposal_id

    def update_proposal_status(
        self,
        proposal_id: UUID,
        status: ProposalStatus,
        reviewer: str = "auto",
    ) -> None:
        """Update the status of a proposal."""
        self._conn.execute(
            "UPDATE proposals SET status = ?, reviewed_at = ?, reviewer = ? WHERE id = ?",
            [status.value, datetime.now(UTC).isoformat(), reviewer, str(proposal_id)],
        )

    def get_pending_proposals(self) -> list[dict[str, Any]]:
        """Get all pending proposals."""
        rows = self._conn.execute(
            "SELECT * FROM proposals WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        cols = [desc[0] for desc in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    def get_proposal(self, proposal_id: UUID) -> dict[str, Any] | None:
        """Get a single proposal by ID."""
        row = self._conn.execute(
            "SELECT * FROM proposals WHERE id = ?", [str(proposal_id)]
        ).fetchone()
        if row is None:
            return None
        cols = [desc[0] for desc in self._conn.description]
        return dict(zip(cols, row))

    def query_proposals(
        self,
        status: str | None = None,
        route: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query proposals with optional filters and pagination."""
        conditions: list[str] = []
        params: list[Any] = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if route:
            conditions.append("route = ?")
            params.append(route)

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM proposals WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._conn.execute(query, params).fetchall()
        cols = [desc[0] for desc in self._conn.description]
        return [dict(zip(cols, row)) for row in rows]

    def update_proposal_data(
        self,
        proposal_id: UUID,
        proposal_data: dict[str, Any] | None = None,
        human_summary: str | None = None,
    ) -> None:
        """Update proposal data and/or human summary."""
        updates = []
        params: list[Any] = []

        if proposal_data is not None:
            updates.append("proposal_data = ?")
            params.append(json.dumps(proposal_data))
        if human_summary is not None:
            updates.append("human_summary = ?")
            params.append(human_summary)

        if updates:
            params.append(str(proposal_id))
            self._conn.execute(
                f"UPDATE proposals SET {', '.join(updates)} WHERE id = ?",
                params,
            )

    def commit_proposal(self, proposal_id: UUID) -> bool:
        """Atomically commit an approved proposal to the graph.

        Creates all proposed nodes and edges in a single transaction.
        Returns True on success, False on failure.
        """
        row = self._conn.execute(
            "SELECT proposal_data, capture_id FROM proposals WHERE id = ?",
            [str(proposal_id)],
        ).fetchone()
        if row is None:
            return False

        proposal_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        capture_id = row[1]

        try:
            self._conn.execute("BEGIN TRANSACTION")

            # Map temp_ids to real UUIDs
            temp_to_real: dict[str, str] = {}

            # Create nodes
            for node_data in proposal_data.get("nodes_to_create", []):
                real_id = str(uuid4())
                temp_to_real[node_data["temp_id"]] = real_id
                node_type = node_data["node_type"]
                networks = node_data.get("networks", [])
                now = datetime.now(UTC).isoformat()

                import hashlib
                content_hash = hashlib.sha256(
                    f"{node_data['title']}|{node_data.get('content', '')}".encode()
                ).hexdigest()

                self._conn.execute(
                    """INSERT INTO nodes (id, node_type, title, content, content_hash,
                       properties, confidence, networks, human_approved, proposed_by,
                       source_capture_id, access_count, decay_score, tags,
                       created_at, updated_at, deleted)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        real_id,
                        node_type,
                        node_data["title"],
                        node_data.get("content", ""),
                        content_hash,
                        json.dumps(node_data.get("properties", {})),
                        node_data.get("confidence", 0.8),
                        networks,
                        False,
                        "archivist",
                        capture_id,
                        0,
                        1.0,
                        [],
                        now,
                        now,
                        False,
                    ],
                )

            # Update existing nodes
            for update in proposal_data.get("nodes_to_update", []):
                node_id = update["node_id"]
                updates = update.get("updates", {})
                set_parts = []
                vals = []
                for k, v in updates.items():
                    if k in ("id", "created_at"):
                        continue
                    if k == "properties":
                        # Merge properties with existing rather than replacing
                        existing_props = {}
                        try:
                            row = self._conn.execute(
                                "SELECT properties FROM nodes WHERE id = ?",
                                [node_id],
                            ).fetchone()
                            if row and row[0]:
                                existing_props = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                        except Exception:
                            pass
                        existing_props.update(v)
                        v = json.dumps(existing_props)
                    elif k == "content":
                        # Append new content to existing for the You node
                        if node_id == YOU_NODE_ID:
                            try:
                                row = self._conn.execute(
                                    "SELECT content FROM nodes WHERE id = ?",
                                    [node_id],
                                ).fetchone()
                                if row and row[0] and row[0] != "Central node representing the user":
                                    v = f"{row[0]}\n{v}"
                            except Exception:
                                pass
                    set_parts.append(f"{k} = ?")
                    vals.append(v)
                if set_parts:
                    set_parts.append("updated_at = ?")
                    vals.append(datetime.now(UTC).isoformat())
                    vals.append(node_id)
                    self._conn.execute(
                        f"UPDATE nodes SET {', '.join(set_parts)} WHERE id = ?",
                        vals,
                    )

            # Create edges
            for edge_data in proposal_data.get("edges_to_create", []):
                edge_id = str(uuid4())
                src = edge_data["source_id"]
                tgt = edge_data["target_id"]
                # Resolve temp IDs
                src = temp_to_real.get(src, src)
                tgt = temp_to_real.get(tgt, tgt)
                now = datetime.now(UTC).isoformat()

                self._conn.execute(
                    """INSERT INTO edges (id, source_id, target_id, edge_type,
                       edge_category, properties, confidence, weight, bidirectional,
                       created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        edge_id,
                        src,
                        tgt,
                        edge_data["edge_type"],
                        edge_data["edge_category"],
                        json.dumps(edge_data.get("properties", {})),
                        edge_data.get("confidence", 0.8),
                        1.0,
                        edge_data.get("bidirectional", False),
                        now,
                        now,
                    ],
                )

            # Mark proposal as approved
            self._conn.execute(
                "UPDATE proposals SET status = ?, reviewed_at = ?, reviewer = ? WHERE id = ?",
                [
                    ProposalStatus.APPROVED.value,
                    datetime.now(UTC).isoformat(),
                    "auto",
                    str(proposal_id),
                ],
            )

            self._conn.execute("COMMIT")
            logger.info("Committed proposal %s", proposal_id)
            return True

        except Exception:
            self._conn.execute("ROLLBACK")
            logger.exception("Failed to commit proposal %s", proposal_id)
            self.update_proposal_status(proposal_id, ProposalStatus.REJECTED, "system_error")
            return False

    # ---- Stats ----

    def get_graph_stats(self) -> dict[str, Any]:
        """Return node count, edge count, and per-type breakdown."""
        node_count = self._conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE deleted = FALSE"
        ).fetchone()[0]
        edge_count = self._conn.execute(
            "SELECT COUNT(*) FROM edges"
        ).fetchone()[0]

        type_breakdown = {}
        rows = self._conn.execute(
            "SELECT node_type, COUNT(*) FROM nodes WHERE deleted = FALSE GROUP BY node_type"
        ).fetchall()
        for row in rows:
            type_breakdown[row[0]] = row[1]

        network_breakdown = {}
        for net in NetworkType:
            count = self._conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE deleted = FALSE AND list_contains(networks, ?)",
                [net.value],
            ).fetchone()[0]
            network_breakdown[net.value] = count

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "type_breakdown": type_breakdown,
            "network_breakdown": network_breakdown,
        }

    # ---- Query helpers (avoid direct _conn access from external code) ----

    def get_latest_health_scores(self) -> list[dict[str, Any]]:
        """Return the latest health snapshot per network."""
        try:
            rows = self._conn.execute(
                """SELECT network, status, momentum, commitment_completion_rate,
                          alert_ratio, staleness_flags, computed_at
                   FROM network_health
                   WHERE (network, computed_at) IN (
                       SELECT network, MAX(computed_at)
                       FROM network_health
                       GROUP BY network
                   )
                   ORDER BY network"""
            ).fetchall()
            cols = ["network", "status", "momentum", "commitment_completion_rate",
                    "alert_ratio", "staleness_flags", "computed_at"]
            return [dict(zip(cols, row)) for row in rows]
        except Exception:
            return []

    def get_recent_bridges(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recently discovered bridges."""
        try:
            rows = self._conn.execute(
                """SELECT source_node_id, target_node_id, source_network,
                          target_network, similarity, meaningful, description
                   FROM bridges ORDER BY discovered_at DESC LIMIT ?""",
                [limit],
            ).fetchall()
            cols = ["source_node_id", "target_node_id", "source_network",
                    "target_network", "similarity", "meaningful", "description"]
            return [dict(zip(cols, row)) for row in rows]
        except Exception:
            return []

    def get_recently_modified_node_ids(self, hours: int = 24) -> list[str]:
        """Return IDs of nodes modified within the given time window."""
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        rows = self._conn.execute(
            "SELECT id FROM nodes WHERE updated_at >= ? AND deleted = FALSE",
            [cutoff],
        ).fetchall()
        return [row[0] for row in rows]

    def get_open_commitments_raw(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return raw open commitment nodes for briefing/alerts."""
        try:
            rows = self._conn.execute(
                """SELECT id, node_type, title, properties
                   FROM nodes
                   WHERE deleted = FALSE
                   AND node_type = 'COMMITMENT'
                   AND json_extract_string(properties, '$.status') = 'open'
                   ORDER BY created_at DESC
                   LIMIT ?""",
                [limit],
            ).fetchall()
            cols = ["id", "node_type", "title", "properties"]
            return [dict(zip(cols, row)) for row in rows]
        except Exception:
            return []

    # ---- Network-level queries ----

    def get_latest_network_health(self, network: str) -> dict[str, Any] | None:
        """Get the latest health snapshot for a network."""
        try:
            row = self._conn.execute(
                """SELECT status, momentum, commitment_completion_rate,
                          alert_ratio, staleness_flags, computed_at
                   FROM network_health
                   WHERE network = ?
                   ORDER BY computed_at DESC LIMIT 1""",
                [network],
            ).fetchone()
            if row:
                return {
                    "status": row[0],
                    "momentum": row[1],
                    "commitment_completion_rate": row[2],
                    "alert_ratio": row[3],
                    "staleness_flags": row[4],
                    "computed_at": row[5],
                }
        except Exception:
            pass
        return None

    def get_network_health_history(
        self, network: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        """Get health history for trend analysis."""
        try:
            rows = self._conn.execute(
                """SELECT status, momentum, commitment_completion_rate,
                          alert_ratio, staleness_flags, computed_at
                   FROM network_health
                   WHERE network = ?
                   ORDER BY computed_at DESC LIMIT ?""",
                [network, limit],
            ).fetchall()
            cols = ["status", "momentum", "commitment_completion_rate",
                    "alert_ratio", "staleness_flags", "computed_at"]
            return [dict(zip(cols, row)) for row in rows]
        except Exception:
            return []

    def get_network_node_count(self, network: str) -> int:
        """Count non-deleted nodes belonging to a network."""
        try:
            result = self._conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE deleted = FALSE AND list_contains(networks, ?)",
                [network],
            ).fetchone()
            return result[0] if result else 0
        except Exception:
            return 0

    def get_recent_network_nodes(
        self, network: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get recent nodes in a network."""
        try:
            rows = self._conn.execute(
                """SELECT id, node_type, title, confidence, decay_score, created_at
                   FROM nodes
                   WHERE deleted = FALSE AND list_contains(networks, ?)
                   ORDER BY created_at DESC LIMIT ?""",
                [network, limit],
            ).fetchall()
            cols = ["id", "node_type", "title", "confidence", "decay_score", "created_at"]
            return [dict(zip(cols, row)) for row in rows]
        except Exception:
            return []

    def get_network_commitment_stats(self, network: str) -> dict[str, Any]:
        """Get commitment statistics for a network."""
        try:
            total = self._conn.execute(
                """SELECT COUNT(*) FROM nodes
                   WHERE deleted = FALSE AND node_type = 'COMMITMENT'
                   AND list_contains(networks, ?)""",
                [network],
            ).fetchone()[0]

            completed = self._conn.execute(
                """SELECT COUNT(*) FROM nodes
                   WHERE deleted = FALSE AND node_type = 'COMMITMENT'
                   AND list_contains(networks, ?)
                   AND json_extract_string(properties, '$.status') = 'completed'""",
                [network],
            ).fetchone()[0]

            open_count = self._conn.execute(
                """SELECT COUNT(*) FROM nodes
                   WHERE deleted = FALSE AND node_type = 'COMMITMENT'
                   AND list_contains(networks, ?)
                   AND json_extract_string(properties, '$.status') = 'open'""",
                [network],
            ).fetchone()[0]

            return {
                "total": total,
                "completed": completed,
                "open": open_count,
                "completion_rate": completed / total if total > 0 else 0.0,
            }
        except Exception:
            return {"total": 0, "completed": 0, "open": 0, "completion_rate": 0.0}

    def get_network_alerts(self, network: str) -> list[dict[str, Any]]:
        """Get active alerts (overdue commitments) for a network."""
        alerts: list[dict[str, Any]] = []
        try:
            rows = self._conn.execute(
                """SELECT id, title, properties FROM nodes
                   WHERE deleted = FALSE AND node_type = 'COMMITMENT'
                   AND list_contains(networks, ?)
                   AND json_extract_string(properties, '$.status') = 'open'""",
                [network],
            ).fetchall()

            from datetime import timezone
            now = datetime.now(timezone.utc)

            for row in rows:
                props = json.loads(row[2]) if isinstance(row[2], str) else (row[2] or {})
                due_date_str = props.get("due_date") or props.get("due_at")
                if due_date_str:
                    try:
                        due_date = datetime.fromisoformat(
                            due_date_str.replace("Z", "+00:00").replace("+00:00", "")
                        )
                        if due_date < now:
                            alerts.append({
                                "type": "overdue_commitment",
                                "node_id": row[0],
                                "title": row[1],
                                "days_overdue": (now - due_date).days,
                            })
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass
        return alerts

    def update_bridge_validation(
        self, bridge_id: str, meaningful: bool, description: str
    ) -> None:
        """Mark a bridge as LLM-validated with a description."""
        self._conn.execute(
            """UPDATE bridges
               SET llm_validated = TRUE, meaningful = ?, description = ?
               WHERE id = ?""",
            [meaningful, description, bridge_id],
        )

    def get_unvalidated_bridges(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return bridges that haven't been LLM-validated yet."""
        try:
            rows = self._conn.execute(
                """SELECT b.id, b.source_node_id, b.target_node_id,
                          b.source_network, b.target_network, b.similarity,
                          n1.title AS source_title, n1.content AS source_content,
                          n2.title AS target_title, n2.content AS target_content
                   FROM bridges b
                   LEFT JOIN nodes n1 ON b.source_node_id = n1.id
                   LEFT JOIN nodes n2 ON b.target_node_id = n2.id
                   WHERE b.llm_validated = FALSE
                   ORDER BY b.discovered_at DESC LIMIT ?""",
                [limit],
            ).fetchall()
            cols = ["id", "source_node_id", "target_node_id", "source_network",
                    "target_network", "similarity", "source_title", "source_content",
                    "target_title", "target_content"]
            return [dict(zip(cols, row)) for row in rows]
        except Exception:
            return []

    # ---- Capture-scoped query helpers ----

    def get_nodes_by_capture_id(self, capture_id: str) -> list[dict[str, Any]]:
        """Return all non-deleted nodes created from a given capture."""
        rows = self._conn.execute(
            """SELECT id, node_type, title, content, networks, properties
               FROM nodes
               WHERE source_capture_id = ? AND deleted = FALSE""",
            [capture_id],
        ).fetchall()
        cols = ["id", "node_type", "title", "content", "networks", "properties"]
        return [dict(zip(cols, row)) for row in rows]

    def get_node_ids_by_capture_id(self, capture_id: str) -> list[str]:
        """Return IDs of all non-deleted nodes created from a given capture."""
        rows = self._conn.execute(
            "SELECT id FROM nodes WHERE source_capture_id = ? AND deleted = FALSE",
            [capture_id],
        ).fetchall()
        return [row[0] for row in rows]

    def get_edges_for_node_ids(self, node_ids: set[str] | list[str]) -> list[dict[str, Any]]:
        """Return all edges where source or target is in *node_ids*."""
        if not node_ids:
            return []
        id_list = list(node_ids)
        placeholders = ", ".join(["?"] * len(id_list))
        rows = self._conn.execute(
            f"""SELECT id, source_id, target_id, edge_type, edge_category,
                       confidence, weight
                FROM edges
                WHERE source_id IN ({placeholders})
                   OR target_id IN ({placeholders})""",
            id_list + id_list,
        ).fetchall()
        cols = ["id", "source_id", "target_id", "edge_type", "edge_category",
                "confidence", "weight"]
        return [dict(zip(cols, row)) for row in rows]

    def get_networks_by_capture_id(self, capture_id: str) -> list[str]:
        """Return distinct networks for nodes created from a capture."""
        rows = self._conn.execute(
            """SELECT DISTINCT UNNEST(networks)
               FROM nodes
               WHERE source_capture_id = ? AND deleted = FALSE""",
            [capture_id],
        ).fetchall()
        return [row[0] for row in rows]

    def get_commitment_nodes_by_capture_id(self, capture_id: str) -> list[dict[str, Any]]:
        """Return commitment nodes with due dates from a capture."""
        rows = self._conn.execute(
            """SELECT id, title, json_extract_string(properties, '$.due_date') AS due_date
               FROM nodes
               WHERE source_capture_id = ? AND deleted = FALSE
               AND node_type = 'COMMITMENT'
               AND json_extract_string(properties, '$.due_date') IS NOT NULL""",
            [capture_id],
        ).fetchall()
        cols = ["id", "title", "due_date"]
        return [dict(zip(cols, row)) for row in rows]

    def get_nodes_for_truth_check(self, capture_id: str) -> list[dict[str, Any]]:
        """Return nodes suitable for truth-layer cross-referencing."""
        rows = self._conn.execute(
            """SELECT id, node_type, title, content, properties
               FROM nodes
               WHERE source_capture_id = ? AND deleted = FALSE""",
            [capture_id],
        ).fetchall()
        cols = ["id", "node_type", "title", "content", "properties"]
        return [dict(zip(cols, row)) for row in rows]

    def find_exact_node_matches(self, node_type: str, title: str) -> list[dict[str, Any]]:
        """Find non-deleted nodes with same type and matching title or aliases.

        Matches exact (case-insensitive), substring containment in either
        direction, first-token match for multi-word names, and alias matches.
        """
        # Exact match + proposed title contained in existing + existing contained in proposed
        # Also search aliases stored in properties->>'aliases'
        first_token = title.strip().split()[0] if title.strip() else title
        rows = self._conn.execute(
            """SELECT DISTINCT id, node_type, title, networks, properties
               FROM nodes
               WHERE deleted = FALSE AND node_type = ? AND (
                   title ILIKE ?
                   OR title ILIKE ?
                   OR ? ILIKE '%' || title || '%'
                   OR (length(?) > 2 AND title ILIKE ?)
                   OR CAST(properties->>'aliases' AS VARCHAR) ILIKE ?
                   OR CAST(properties->>'aliases' AS VARCHAR) ILIKE ?
               )""",
            [node_type, title, f"%{title}%", title, first_token, f"{first_token}%",
             f"%{title}%", f"%{first_token}%"],
        ).fetchall()
        cols = ["id", "node_type", "title", "networks", "properties"]
        return [dict(zip(cols, row)) for row in rows]

    def get_node_created_at(self, node_id: str) -> datetime | None:
        """Return created_at for a single node."""
        row = self._conn.execute(
            "SELECT created_at FROM nodes WHERE id = ?", [node_id]
        ).fetchone()
        return row[0] if row else None

    def get_node_created_at_batch(self, node_ids: list[str]) -> dict[str, datetime]:
        """Return {node_id: created_at} for a list of node IDs."""
        if not node_ids:
            return {}
        placeholders = ", ".join(["?"] * len(node_ids))
        rows = self._conn.execute(
            f"SELECT id, created_at FROM nodes WHERE id IN ({placeholders})",
            node_ids,
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    # ---- Person merge ----

    def merge_person_nodes(self, source_id: str, target_id: str) -> None:
        """Merge source person node into target: transfer edges, merge aliases, soft-delete source.

        - Transfers all edges from source to target (rewriting source_id/target_id)
        - Removes duplicate edges (same source+target+edge_type after transfer)
        - Merges source's title and aliases into target's aliases
        - Merges networks
        - Soft-deletes the source node
        """
        now = datetime.now(UTC).isoformat()

        # Load both nodes
        source = self.get_node(UUID(source_id))
        target = self.get_node(UUID(target_id))
        if not source or not target:
            raise ValueError("Both source and target nodes must exist")

        # 1. Transfer edges: rewrite source_id references to target_id
        self._conn.execute(
            "UPDATE edges SET source_id = ?, updated_at = ? WHERE source_id = ?",
            [target_id, now, source_id],
        )
        self._conn.execute(
            "UPDATE edges SET target_id = ?, updated_at = ? WHERE target_id = ?",
            [target_id, now, source_id],
        )

        # Remove self-loops that may have been created
        self._conn.execute(
            "DELETE FROM edges WHERE source_id = ? AND target_id = ?",
            [target_id, target_id],
        )

        # Remove duplicate edges (keep the one with highest weight)
        self._conn.execute(
            """DELETE FROM edges WHERE id IN (
                SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY source_id, target_id, edge_type
                        ORDER BY weight DESC, created_at ASC
                    ) AS rn FROM edges
                    WHERE source_id = ? OR target_id = ?
                ) WHERE rn > 1
            )""",
            [target_id, target_id],
        )

        # 2. Merge aliases: add source title + source aliases into target aliases
        target_props = target.properties if isinstance(target.properties, dict) else {}
        source_props = source.properties if isinstance(source.properties, dict) else {}

        existing_aliases = list(target_props.get("aliases", []))
        source_aliases = list(source_props.get("aliases", []))
        names_to_add = [source.title] + source_aliases

        existing_lower = {a.lower() for a in existing_aliases} | {target.title.lower()}
        for name in names_to_add:
            if name.strip() and name.lower().strip() not in existing_lower:
                existing_aliases.append(name.strip())
                existing_lower.add(name.lower().strip())

        target_props["aliases"] = existing_aliases
        self._conn.execute(
            "UPDATE nodes SET properties = ?, updated_at = ? WHERE id = ?",
            [json.dumps(target_props), now, target_id],
        )

        # 3. Merge networks
        target_nets = set(n.value if hasattr(n, "value") else n for n in target.networks)
        source_nets = set(n.value if hasattr(n, "value") else n for n in source.networks)
        merged_nets = list(target_nets | source_nets)
        if merged_nets != list(target_nets):
            self._conn.execute(
                "UPDATE nodes SET networks = ?, updated_at = ? WHERE id = ?",
                [merged_nets, now, target_id],
            )

        # 4. Soft-delete the source node
        self.delete_node(UUID(source_id))

    # ---- Dossier / search helpers ----

    def search_by_title(self, query: str, limit: int = 20) -> list[BaseNode]:
        """Find nodes whose title or aliases contain the query string (case-insensitive)."""
        rows = self._conn.execute(
            """SELECT * FROM nodes WHERE deleted = FALSE
               AND (title ILIKE ?
                    OR CAST(properties->>'aliases' AS VARCHAR) ILIKE ?)
               ORDER BY confidence DESC, access_count DESC LIMIT ?""",
            [f"%{query}%", f"%{query}%", limit],
        ).fetchall()
        return [self._row_to_node(row) for row in rows]

    # ---- Health scoring queries ----

    def get_commitment_completion_rate(self, network: str) -> tuple[int, int]:
        """Return (completed_count, total_count) for commitments in a network."""
        row = self._conn.execute(
            """SELECT
                   COUNT(*) FILTER (WHERE json_extract_string(properties, '$.status') = 'completed') AS done,
                   COUNT(*) AS total
               FROM nodes
               WHERE deleted = FALSE
                 AND node_type = 'COMMITMENT'
                 AND list_contains(networks, ?)""",
            [network],
        ).fetchone()
        return (row[0], row[1]) if row else (0, 0)

    def get_commitment_alert_counts(self, network: str, now_iso: str) -> tuple[int, int]:
        """Return (overdue_count, open_total) for commitments in a network."""
        row = self._conn.execute(
            """SELECT
                   COUNT(*) FILTER (
                       WHERE json_extract_string(properties, '$.status') = 'open'
                         AND json_extract_string(properties, '$.due_date') < ?
                   ) AS overdue,
                   COUNT(*) FILTER (
                       WHERE json_extract_string(properties, '$.status') = 'open'
                   ) AS open_total
               FROM nodes
               WHERE deleted = FALSE
                 AND node_type = 'COMMITMENT'
                 AND list_contains(networks, ?)""",
            [now_iso, network],
        ).fetchone()
        return (row[0], row[1]) if row else (0, 0)

    def get_staleness_count(self, network: str, threshold: float) -> int:
        """Count nodes in a network with decay_score below threshold."""
        row = self._conn.execute(
            """SELECT COUNT(*)
               FROM nodes
               WHERE deleted = FALSE
                 AND decay_score < ?
                 AND list_contains(networks, ?)""",
            [threshold, network],
        ).fetchone()
        return row[0] if row else 0

    def store_health_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Persist a health snapshot into the network_health table."""
        self._conn.execute(
            """INSERT INTO network_health
               (id, network, status, momentum, commitment_completion_rate,
                alert_ratio, staleness_flags, computed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                snapshot["id"],
                snapshot["network"],
                snapshot["status"],
                snapshot["momentum"],
                snapshot["commitment_completion_rate"],
                snapshot["alert_ratio"],
                snapshot["staleness_flags"],
                snapshot["computed_at"],
            ],
        )

    # ---- Spaced repetition queries ----

    def update_node_review_date(self, node_id: str, review_date: str) -> None:
        """Update the review_date and updated_at columns for a node."""
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "UPDATE nodes SET review_date = ?, updated_at = ? WHERE id = ?",
            [review_date, now, node_id],
        )

    def get_review_due_nodes(self, cutoff_iso: str) -> list[dict[str, Any]]:
        """Return nodes due for review (review_date <= cutoff)."""
        rows = self._conn.execute(
            """SELECT id, node_type, title, properties, review_date
               FROM nodes
               WHERE deleted = FALSE
                 AND review_date IS NOT NULL
                 AND review_date <= ?
               ORDER BY review_date ASC""",
            [cutoff_iso],
        ).fetchall()
        cols = ["id", "node_type", "title", "properties", "review_date"]
        return [dict(zip(cols, row)) for row in rows]

    def get_node_properties_raw(self, node_id: str) -> str | None:
        """Return the raw properties JSON string for a node."""
        row = self._conn.execute(
            "SELECT properties FROM nodes WHERE id = ?",
            [node_id],
        ).fetchone()
        return row[0] if row else None

    def update_node_properties_raw(self, node_id: str, properties_json: str) -> None:
        """Overwrite a node's properties with a JSON string."""
        self._conn.execute(
            "UPDATE nodes SET properties = ?, updated_at = ? WHERE id = ?",
            [properties_json, datetime.now(UTC).isoformat(), node_id],
        )

    # ---- Gap detection queries ----

    def find_orphaned_nodes(self) -> list[dict[str, Any]]:
        """Find nodes with zero edges (neither source nor target)."""
        rows = self._conn.execute(
            """SELECT n.id, n.node_type, n.title, n.created_at
               FROM nodes n
               LEFT JOIN edges e_src ON e_src.source_id = n.id
               LEFT JOIN edges e_tgt ON e_tgt.target_id = n.id
               WHERE n.deleted = FALSE
                 AND e_src.id IS NULL
                 AND e_tgt.id IS NULL
                 AND n.id != ?
               ORDER BY n.created_at ASC""",
            [YOU_NODE_ID],
        ).fetchall()
        cols = ["id", "node_type", "title", "created_at"]
        return [dict(zip(cols, row)) for row in rows]

    def find_stalled_active_nodes(self, node_type: str, cutoff_iso: str) -> list[dict[str, Any]]:
        """Find active nodes of a type with no recent edge activity."""
        rows = self._conn.execute(
            """SELECT n.id, n.title, n.properties, n.updated_at
               FROM nodes n
               WHERE n.deleted = FALSE
                 AND n.node_type = ?
                 AND json_extract_string(n.properties, '$.status') = 'active'
                 AND NOT EXISTS (
                     SELECT 1 FROM edges e
                     WHERE (e.source_id = n.id OR e.target_id = n.id)
                       AND e.created_at >= ?
                 )
               ORDER BY n.updated_at ASC""",
            [node_type, cutoff_iso],
        ).fetchall()
        cols = ["id", "title", "properties", "updated_at"]
        return [dict(zip(cols, row)) for row in rows]

    def find_isolated_concepts(self) -> list[dict[str, Any]]:
        """Find CONCEPT nodes not linked to any EVENT, PROJECT, or COMMITMENT."""
        rows = self._conn.execute(
            """SELECT n.id, n.title, n.properties, n.created_at
               FROM nodes n
               WHERE n.deleted = FALSE
                 AND n.node_type = 'CONCEPT'
                 AND NOT EXISTS (
                     SELECT 1 FROM edges e
                     JOIN nodes n2 ON (
                         (e.source_id = n.id AND e.target_id = n2.id)
                         OR (e.target_id = n.id AND e.source_id = n2.id)
                     )
                     WHERE n2.node_type IN ('EVENT', 'PROJECT', 'COMMITMENT')
                 )
               ORDER BY n.created_at ASC"""
        ).fetchall()
        cols = ["id", "title", "properties", "created_at"]
        return [dict(zip(cols, row)) for row in rows]

    def find_unresolved_decisions(self) -> list[dict[str, Any]]:
        """Find DECISION nodes with no outcome recorded."""
        rows = self._conn.execute(
            """SELECT id, title, properties, created_at
               FROM nodes
               WHERE deleted = FALSE
                 AND node_type = 'DECISION'
                 AND (
                     json_extract_string(properties, '$.outcome') IS NULL
                     OR json_extract_string(properties, '$.outcome') = ''
                 )
               ORDER BY created_at ASC"""
        ).fetchall()
        cols = ["id", "title", "properties", "created_at"]
        return [dict(zip(cols, row)) for row in rows]

    # ---- Decay queries ----

    def get_all_nodes_for_decay(self) -> list[tuple]:
        """Return (id, last_accessed, networks, node_type, properties, created_at, access_count) for all non-deleted, non-You nodes."""
        return self._conn.execute(
            """SELECT id, last_accessed, networks, node_type, properties, created_at, access_count
               FROM nodes
               WHERE deleted = FALSE AND id != ?""",
            [YOU_NODE_ID],
        ).fetchall()

    def update_node_decay_score(self, node_id: str, score: float) -> None:
        """Update a node's decay_score."""
        self._conn.execute(
            "UPDATE nodes SET decay_score = ?, updated_at = ? WHERE id = ?",
            [score, datetime.now(UTC).isoformat(), node_id],
        )

    def get_nodes_below_decay(self, threshold: float) -> list[dict[str, Any]]:
        """Return nodes whose decay_score has fallen below threshold."""
        rows = self._conn.execute(
            """SELECT id, node_type, title, decay_score, last_accessed, networks
               FROM nodes
               WHERE deleted = FALSE AND decay_score < ? AND id != ?
               ORDER BY decay_score ASC""",
            [threshold, YOU_NODE_ID],
        ).fetchall()
        cols = ["id", "node_type", "title", "decay_score", "last_accessed", "networks"]
        return [dict(zip(cols, row)) for row in rows]

    # ---- Bridge queries ----

    def bridge_exists(self, source_id: str, target_id: str) -> bool:
        """Check if a bridge between two nodes already exists (either direction)."""
        count = self._conn.execute(
            """SELECT COUNT(*) FROM bridges
               WHERE (source_node_id = ? AND target_node_id = ?)
               OR (source_node_id = ? AND target_node_id = ?)""",
            [source_id, target_id, target_id, source_id],
        ).fetchone()[0]
        return count > 0

    def store_bridge(self, bridge: dict[str, Any]) -> None:
        """Store a discovered bridge in the bridges table."""
        self._conn.execute(
            """INSERT INTO bridges
               (id, source_node_id, target_node_id, source_network,
                target_network, similarity, llm_validated, meaningful,
                description, discovered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                bridge["id"],
                bridge["source_node_id"],
                bridge["target_node_id"],
                bridge["source_network"],
                bridge["target_network"],
                bridge["similarity"],
                bridge.get("llm_validated", False),
                bridge.get("meaningful"),
                bridge.get("description"),
                bridge["discovered_at"],
            ],
        )

    def query_bridges(
        self,
        network: str | None = None,
        validated_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query discovered bridges with optional filters."""
        conditions = []
        params: list[Any] = []
        if network:
            conditions.append("(source_network = ? OR target_network = ?)")
            params.extend([network, network])
        if validated_only:
            conditions.append("llm_validated = TRUE AND meaningful = TRUE")
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self._conn.execute(
            f"""SELECT id, source_node_id, target_node_id, source_network,
                       target_network, similarity, llm_validated, meaningful,
                       description, discovered_at
                FROM bridges WHERE {where}
                ORDER BY similarity DESC LIMIT ?""",
            params + [limit],
        ).fetchall()
        cols = [
            "id", "source_node_id", "target_node_id", "source_network",
            "target_network", "similarity", "llm_validated", "meaningful",
            "description", "discovered_at",
        ]
        return [dict(zip(cols, row)) for row in rows]

    # ---- Relationship decay queries ----

    def get_person_nodes(self) -> list[dict[str, Any]]:
        """Return all non-deleted PERSON nodes."""
        rows = self._conn.execute(
            """SELECT id, title, properties, last_accessed, networks
               FROM nodes
               WHERE deleted = FALSE AND node_type = 'PERSON'"""
        ).fetchall()
        cols = ["id", "title", "properties", "last_accessed", "networks"]
        return [dict(zip(cols, row)) for row in rows]

    def get_person_commitments(self, person_node_id: str) -> list[dict[str, Any]]:
        """Return open commitments connected to a person node."""
        rows = self._conn.execute(
            """SELECT n.id, n.title, n.properties
               FROM nodes n
               JOIN edges e ON (
                   (e.source_id = ? AND e.target_id = n.id)
                   OR (e.target_id = ? AND e.source_id = n.id)
               )
               WHERE n.deleted = FALSE
                 AND n.node_type = 'COMMITMENT'
                 AND json_extract_string(n.properties, '$.status') = 'open'""",
            [person_node_id, person_node_id],
        ).fetchall()
        cols = ["id", "title", "properties"]
        return [dict(zip(cols, row)) for row in rows]

    # ---- Commitment scan queries ----

    def get_open_commitments_detailed(self) -> list[dict[str, Any]]:
        """Return all open commitment nodes with full details."""
        rows = self._conn.execute(
            """SELECT id, title, content, properties, networks, created_at
               FROM nodes
               WHERE deleted = FALSE
                 AND node_type = 'COMMITMENT'
                 AND json_extract_string(properties, '$.status') = 'open'""",
        ).fetchall()
        cols = ["id", "title", "content", "properties", "networks", "created_at"]
        return [dict(zip(cols, row)) for row in rows]

    # ---- CLI query helpers ----

    def find_node_ids_by_prefix(self, prefix: str) -> list[str]:
        """Find node IDs matching a UUID prefix."""
        rows = self._conn.execute(
            "SELECT id FROM nodes WHERE deleted = FALSE AND CAST(id AS VARCHAR) LIKE ?",
            [f"{prefix}%"],
        ).fetchall()
        return [row[0] for row in rows]

    def find_proposals_by_id_prefix(self, prefix: str) -> list[str]:
        """Find pending proposal IDs matching a prefix."""
        rows = self._conn.execute(
            "SELECT id FROM proposals WHERE CAST(id AS VARCHAR) LIKE ? AND status = 'pending'",
            [f"{prefix}%"],
        ).fetchall()
        return [row[0] for row in rows]

    def search_nodes_ilike(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search nodes by title (case-insensitive LIKE match)."""
        rows = self._conn.execute(
            "SELECT id, node_type, title, content, networks, confidence, created_at "
            "FROM nodes WHERE deleted = FALSE AND title ILIKE ? LIMIT ?",
            [f"%{query}%", limit],
        ).fetchall()
        cols = ["id", "node_type", "title", "content", "networks", "confidence", "created_at"]
        return [dict(zip(cols, row)) for row in rows]

    def get_truth_layer_conn(self):
        """Return the underlying connection for TruthLayer initialization."""
        return self._conn

    # ---- Actions (kinetic operations) ----

    def record_action(self, action: dict[str, Any]) -> str:
        """Record an executed action in the actions table."""
        self._conn.execute(
            """INSERT INTO actions (id, action_type, status, source_node_id,
               target_node_id, params, result, executed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                action["id"],
                action["action_type"],
                action.get("status", "completed"),
                action.get("source_node_id"),
                action.get("target_node_id"),
                json.dumps(action.get("params", {})),
                json.dumps(action.get("result", {})),
                action.get("executed_at", datetime.now(UTC).isoformat()),
            ],
        )
        return action["id"]

    def get_action_history(
        self, limit: int = 50, action_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Query action history with optional type filter."""
        conditions = []
        params: list[Any] = []
        if action_type:
            conditions.append("action_type = ?")
            params.append(action_type)
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self._conn.execute(
            f"""SELECT id, action_type, status, source_node_id, target_node_id,
                       params, result, executed_at
                FROM actions WHERE {where}
                ORDER BY executed_at DESC LIMIT ?""",
            params + [limit],
        ).fetchall()
        cols = ["id", "action_type", "status", "source_node_id", "target_node_id",
                "params", "result", "executed_at"]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            if isinstance(d["params"], str):
                d["params"] = json.loads(d["params"])
            if isinstance(d["result"], str):
                d["result"] = json.loads(d["result"])
            result.append(d)
        return result

    def get_actions_for_node(self, node_id: str) -> list[dict[str, Any]]:
        """Get all actions involving a specific node."""
        rows = self._conn.execute(
            """SELECT id, action_type, status, source_node_id, target_node_id,
                      params, result, executed_at
               FROM actions
               WHERE source_node_id = ? OR target_node_id = ?
               ORDER BY executed_at DESC""",
            [node_id, node_id],
        ).fetchall()
        cols = ["id", "action_type", "status", "source_node_id", "target_node_id",
                "params", "result", "executed_at"]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            if isinstance(d["params"], str):
                d["params"] = json.loads(d["params"])
            if isinstance(d["result"], str):
                d["result"] = json.loads(d["result"])
            result.append(d)
        return result

    # ---- Outcomes (feedback loop) ----

    def record_outcome(self, outcome: dict[str, Any]) -> str:
        """Record an outcome for a node."""
        self._conn.execute(
            """INSERT INTO outcomes (id, node_id, node_type, outcome_text,
               rating, evidence, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                outcome["id"],
                outcome["node_id"],
                outcome["node_type"],
                outcome["outcome_text"],
                outcome["rating"],
                json.dumps(outcome.get("evidence", [])),
                outcome.get("recorded_at", datetime.now(UTC).isoformat()),
            ],
        )
        return outcome["id"]

    def get_outcomes_for_node(self, node_id: str) -> list[dict[str, Any]]:
        """Get all outcomes recorded for a node."""
        rows = self._conn.execute(
            """SELECT id, node_id, node_type, outcome_text, rating, evidence, recorded_at
               FROM outcomes WHERE node_id = ?
               ORDER BY recorded_at DESC""",
            [node_id],
        ).fetchall()
        cols = ["id", "node_id", "node_type", "outcome_text", "rating", "evidence", "recorded_at"]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            if isinstance(d["evidence"], str):
                d["evidence"] = json.loads(d["evidence"])
            result.append(d)
        return result

    def get_pending_outcomes(self, days_threshold: int = 14) -> list[dict[str, Any]]:
        """Get decisions/goals/commitments older than threshold without outcomes."""
        cutoff = (datetime.now(UTC) - timedelta(days=days_threshold)).isoformat()
        rows = self._conn.execute(
            """SELECT n.id, n.node_type, n.title, n.properties, n.created_at
               FROM nodes n
               WHERE n.deleted = FALSE
                 AND n.node_type IN ('DECISION', 'GOAL', 'COMMITMENT')
                 AND n.created_at <= ?
                 AND NOT EXISTS (
                     SELECT 1 FROM outcomes o WHERE o.node_id = n.id
                 )
               ORDER BY n.created_at ASC""",
            [cutoff],
        ).fetchall()
        cols = ["id", "node_type", "title", "properties", "created_at"]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            d["properties"] = parse_properties(d["properties"])
            result.append(d)
        return result

    def get_outcome_stats(self, network: str | None = None) -> dict[str, Any]:
        """Get outcome statistics, optionally filtered by network."""
        if network:
            rows = self._conn.execute(
                """SELECT o.rating, COUNT(*) as cnt
                   FROM outcomes o
                   JOIN nodes n ON o.node_id = n.id
                   WHERE n.deleted = FALSE AND list_contains(n.networks, ?)
                   GROUP BY o.rating""",
                [network],
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT rating, COUNT(*) as cnt FROM outcomes GROUP BY rating"
            ).fetchall()

        stats: dict[str, int] = {}
        total = 0
        for row in rows:
            stats[row[0]] = row[1]
            total += row[1]

        return {
            "total": total,
            "by_rating": stats,
            "positive_rate": stats.get("positive", 0) / total if total > 0 else 0.0,
        }

    # ---- Pattern detection ----

    def store_pattern(self, pattern: dict[str, Any]) -> str:
        """Store a detected pattern, deduplicating by pattern_type + description.

        If an active pattern with the same type and description exists, update it
        (bump last_confirmed, update confidence/evidence). Otherwise insert new.
        """
        existing = self.find_matching_pattern(
            pattern["pattern_type"], pattern["description"]
        )
        if existing:
            self.update_pattern_confirmation(
                existing["id"],
                confidence=pattern.get("confidence"),
                evidence=pattern.get("evidence"),
                suggested_action=pattern.get("suggested_action"),
                severity=pattern.get("severity"),
                previous_value=pattern.get("previous_value"),
                current_value=pattern.get("current_value"),
                description=pattern.get("description"),
            )
            return existing["id"]

        self._conn.execute(
            """INSERT INTO detected_patterns (id, pattern_type, description, evidence,
               confidence, suggested_action, networks, first_detected, last_confirmed,
               status, severity, previous_value, current_value, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                pattern["id"],
                pattern["pattern_type"],
                pattern["description"],
                json.dumps(pattern.get("evidence", [])),
                pattern.get("confidence", 0.5),
                pattern.get("suggested_action", ""),
                json.dumps(pattern.get("networks", [])),
                pattern.get("first_detected", datetime.now(UTC).isoformat()),
                pattern.get("last_confirmed", datetime.now(UTC).isoformat()),
                pattern.get("status", "active"),
                pattern.get("severity", "info"),
                pattern.get("previous_value"),
                pattern.get("current_value"),
                pattern.get("created_at", datetime.now(UTC).isoformat()),
            ],
        )
        return pattern["id"]

    def find_matching_pattern(
        self, pattern_type: str, description: str
    ) -> dict[str, Any] | None:
        """Find an active pattern with matching type and description."""
        rows = self._conn.execute(
            """SELECT id, pattern_type, description, evidence, confidence,
                      suggested_action, networks, first_detected, last_confirmed,
                      status, severity, previous_value, current_value
               FROM detected_patterns
               WHERE pattern_type = ? AND description = ? AND status = 'active'
               LIMIT 1""",
            [pattern_type, description],
        ).fetchall()
        if not rows:
            return None
        cols = ["id", "pattern_type", "description", "evidence", "confidence",
                "suggested_action", "networks", "first_detected", "last_confirmed",
                "status", "severity", "previous_value", "current_value"]
        d = dict(zip(cols, rows[0]))
        if isinstance(d["evidence"], str):
            d["evidence"] = json.loads(d["evidence"])
        if isinstance(d["networks"], str):
            d["networks"] = json.loads(d["networks"])
        return d

    def resolve_pattern(self, pattern_id: str, reason: str = "resolved") -> None:
        """Mark a pattern as resolved."""
        self._conn.execute(
            "UPDATE detected_patterns SET status = 'resolved' WHERE id = ?",
            [pattern_id],
        )

    def expire_stale_patterns(self, max_age_days: int = 30) -> int:
        """Auto-expire active patterns not confirmed within max_age_days. Returns count expired."""
        cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
        result = self._conn.execute(
            """UPDATE detected_patterns SET status = 'expired'
               WHERE status = 'active' AND last_confirmed < ?""",
            [cutoff],
        )
        # DuckDB returns rowcount via fetchone after UPDATE
        try:
            return result.fetchone()[0] if result else 0
        except Exception:
            return 0

    def get_active_pattern_types(self) -> list[dict[str, Any]]:
        """Get all active patterns grouped by type for lifecycle comparison."""
        rows = self._conn.execute(
            """SELECT id, pattern_type, description, confidence, current_value
               FROM detected_patterns WHERE status = 'active'"""
        ).fetchall()
        cols = ["id", "pattern_type", "description", "confidence", "current_value"]
        return [dict(zip(cols, row)) for row in rows]

    def get_patterns(
        self, pattern_type: str | None = None, status: str = "active", limit: int = 50
    ) -> list[dict[str, Any]]:
        """Query detected patterns."""
        conditions = ["status = ?"]
        params: list[Any] = [status]
        if pattern_type:
            conditions.append("pattern_type = ?")
            params.append(pattern_type)
        where = " AND ".join(conditions)
        rows = self._conn.execute(
            f"""SELECT id, pattern_type, description, evidence, confidence,
                       suggested_action, networks, first_detected, last_confirmed,
                       status, severity, previous_value, current_value, created_at
                FROM detected_patterns WHERE {where}
                ORDER BY confidence DESC, last_confirmed DESC LIMIT ?""",
            params + [limit],
        ).fetchall()
        cols = ["id", "pattern_type", "description", "evidence", "confidence",
                "suggested_action", "networks", "first_detected", "last_confirmed",
                "status", "severity", "previous_value", "current_value", "created_at"]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            if isinstance(d["evidence"], str):
                d["evidence"] = json.loads(d["evidence"])
            if isinstance(d["networks"], str):
                d["networks"] = json.loads(d["networks"])
            result.append(d)
        return result

    def update_pattern_confirmation(
        self,
        pattern_id: str,
        confidence: float | None = None,
        evidence: list[str] | None = None,
        suggested_action: str | None = None,
        severity: str | None = None,
        previous_value: float | None = None,
        current_value: float | None = None,
        description: str | None = None,
    ) -> None:
        """Update a pattern's last_confirmed timestamp and optionally its fields."""
        sets = ["last_confirmed = ?"]
        params: list[Any] = [datetime.now(UTC).isoformat()]
        if confidence is not None:
            sets.append("confidence = ?")
            params.append(confidence)
        if evidence is not None:
            sets.append("evidence = ?")
            params.append(json.dumps(evidence))
        if suggested_action is not None:
            sets.append("suggested_action = ?")
            params.append(suggested_action)
        if severity is not None:
            sets.append("severity = ?")
            params.append(severity)
        if previous_value is not None:
            sets.append("previous_value = ?")
            params.append(previous_value)
        if current_value is not None:
            sets.append("current_value = ?")
            params.append(current_value)
        if description is not None:
            sets.append("description = ?")
            params.append(description)
        params.append(pattern_id)
        self._conn.execute(
            f"UPDATE detected_patterns SET {', '.join(sets)} WHERE id = ?",
            params,
        )

    # ---- Timeline queries ----

    def get_nodes_by_date_range(
        self,
        start: str | None = None,
        end: str | None = None,
        networks: list[str] | None = None,
        node_types: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get nodes within a date range, sorted chronologically."""
        conditions = ["deleted = FALSE"]
        params: list[Any] = []

        if start:
            conditions.append("created_at >= ?")
            params.append(start)
        if end:
            conditions.append("created_at <= ?")
            params.append(end)
        if networks:
            net_conds = ["list_contains(networks, ?)"] * len(networks)
            conditions.append(f"({' OR '.join(net_conds)})")
            params.extend(networks)
        if node_types:
            placeholders = ", ".join(["?"] * len(node_types))
            conditions.append(f"node_type IN ({placeholders})")
            params.extend(node_types)

        where = " AND ".join(conditions)
        rows = self._conn.execute(
            f"""SELECT id, node_type, title, content, properties, networks,
                       confidence, created_at
                FROM nodes WHERE {where}
                ORDER BY created_at ASC LIMIT ?""",
            params + [limit],
        ).fetchall()
        cols = ["id", "node_type", "title", "content", "properties", "networks",
                "confidence", "created_at"]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            d["properties"] = parse_properties(d["properties"])
            result.append(d)
        return result

    def get_temporal_neighbors(
        self, node_id: str, edge_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Get nodes connected via temporal edges (PRECEDED_BY, TRIGGERED, EVOLVED_INTO)."""
        temporal_types = edge_types or ["PRECEDED_BY", "TRIGGERED", "EVOLVED_INTO", "CONCURRENT_WITH"]
        placeholders = ", ".join(["?"] * len(temporal_types))
        rows = self._conn.execute(
            f"""SELECT e.id as edge_id, e.edge_type, e.source_id, e.target_id,
                       n.id as node_id, n.node_type, n.title, n.created_at
                FROM edges e
                JOIN nodes n ON (
                    CASE WHEN e.source_id = ? THEN e.target_id ELSE e.source_id END = n.id
                )
                WHERE (e.source_id = ? OR e.target_id = ?)
                  AND e.edge_type IN ({placeholders})
                  AND n.deleted = FALSE
                ORDER BY n.created_at ASC""",
            [node_id, node_id, node_id] + temporal_types,
        ).fetchall()
        cols = ["edge_id", "edge_type", "source_id", "target_id",
                "node_id", "node_type", "title", "created_at"]
        return [dict(zip(cols, row)) for row in rows]

    # ---- Investigation queries ----

    def find_shortest_path(self, source_id: str, target_id: str, max_depth: int = 6) -> list[str] | None:
        """BFS shortest path between two nodes. Returns list of node IDs or None."""
        if source_id == target_id:
            return [source_id]

        visited = {source_id}
        queue = [(source_id, [source_id])]

        for _ in range(max_depth):
            next_queue = []
            if not queue:
                break
            batch_ids = [nid for nid, _ in queue]
            edges = self.get_edges_batch(batch_ids)

            edge_map: dict[str, list[str]] = {}
            for e in edges:
                src, tgt = str(e.source_id), str(e.target_id)
                edge_map.setdefault(src, []).append(tgt)
                edge_map.setdefault(tgt, []).append(src)

            for node_id, path in queue:
                for neighbor in edge_map.get(node_id, []):
                    if neighbor == target_id:
                        return path + [neighbor]
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_queue.append((neighbor, path + [neighbor]))
            queue = next_queue

        return None

    def get_filtered_neighborhood(
        self,
        node_id: str,
        hops: int = 1,
        node_types: list[str] | None = None,
        edge_types: list[str] | None = None,
        networks: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get filtered neighborhood around a node."""
        subgraph = self.get_neighborhood(UUID(node_id), hops=hops)

        filtered_nodes = []
        for node in subgraph.nodes:
            if node_types and node.node_type.value not in node_types:
                continue
            if networks:
                node_nets = [n.value for n in node.networks]
                if not any(net in node_nets for net in networks):
                    continue
            filtered_nodes.append(node)

        filtered_node_ids = {str(n.id) for n in filtered_nodes}
        filtered_edges = []
        for edge in subgraph.edges:
            if edge_types and edge.edge_type.value not in edge_types:
                continue
            src, tgt = str(edge.source_id), str(edge.target_id)
            if src in filtered_node_ids or tgt in filtered_node_ids:
                filtered_edges.append(edge)

        return {
            "nodes": [n.model_dump(mode="json") for n in filtered_nodes],
            "edges": [e.model_dump(mode="json") for e in filtered_edges],
        }

    def get_shared_connections(self, node_ids: list[str]) -> list[dict[str, Any]]:
        """Find nodes connected to ALL of the given nodes."""
        if not node_ids or len(node_ids) < 2:
            return []

        # For each input node, get its neighbors
        neighbor_sets: list[set[str]] = []
        for nid in node_ids:
            edges = self.get_edges(UUID(nid))
            neighbors = set()
            for e in edges:
                src, tgt = str(e.source_id), str(e.target_id)
                neighbors.add(tgt if src == nid else src)
            neighbor_sets.append(neighbors)

        # Intersect all neighbor sets
        common = neighbor_sets[0]
        for ns in neighbor_sets[1:]:
            common = common & ns

        # Remove the input nodes themselves
        common -= set(node_ids)

        if not common:
            return []

        nodes = self.get_nodes_batch(list(common))
        return [
            {"id": str(n.id), "node_type": n.node_type.value, "title": n.title}
            for n in nodes.values()
        ]

    # ---- Cross-feature integration queries ----

    def count_nodes_by_status(self, node_type: str, status: str) -> int:
        """Count nodes of a type with a given status property."""
        try:
            row = self._conn.execute(
                """SELECT COUNT(*) FROM nodes
                   WHERE deleted = FALSE AND node_type = ?
                   AND json_extract_string(properties, '$.status') = ?""",
                [node_type, status],
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def get_actions_by_date_range(
        self,
        start: str | None = None,
        end: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get actions within a date range, sorted chronologically."""
        conditions: list[str] = []
        params: list[Any] = []
        if start:
            conditions.append("executed_at >= ?")
            params.append(start)
        if end:
            conditions.append("executed_at <= ?")
            params.append(end)
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self._conn.execute(
            f"""SELECT id, action_type, status, source_node_id, target_node_id,
                       params, result, executed_at
                FROM actions WHERE {where}
                ORDER BY executed_at ASC LIMIT ?""",
            params + [limit],
        ).fetchall()
        cols = ["id", "action_type", "status", "source_node_id", "target_node_id",
                "params", "result", "executed_at"]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            if isinstance(d["params"], str):
                d["params"] = json.loads(d["params"])
            if isinstance(d["result"], str):
                d["result"] = json.loads(d["result"])
            result.append(d)
        return result

    def get_bridges_for_nodes(self, node_ids: list[str], limit: int = 50) -> list[dict[str, Any]]:
        """Get bridges involving any of the given node IDs."""
        if not node_ids:
            return []
        placeholders = ", ".join(["?"] * len(node_ids))
        rows = self._conn.execute(
            f"""SELECT id, source_node_id, target_node_id, source_network,
                       target_network, similarity, llm_validated, meaningful,
                       description, discovered_at
                FROM bridges
                WHERE source_node_id IN ({placeholders})
                   OR target_node_id IN ({placeholders})
                ORDER BY similarity DESC LIMIT ?""",
            node_ids + node_ids + [limit],
        ).fetchall()
        cols = [
            "id", "source_node_id", "target_node_id", "source_network",
            "target_network", "similarity", "llm_validated", "meaningful",
            "description", "discovered_at",
        ]
        return [dict(zip(cols, row)) for row in rows]

    def get_nodes_with_best_date(
        self,
        start: str | None = None,
        end: str | None = None,
        networks: list[str] | None = None,
        node_types: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get nodes sorted by best available date per type.

        Uses event_date for EVENTs, decision_date for DECISIONs, due_date for
        COMMITMENTs, and created_at as fallback.
        """
        conditions = ["deleted = FALSE"]
        params: list[Any] = []

        if networks:
            net_conds = ["list_contains(networks, ?)"] * len(networks)
            conditions.append(f"({' OR '.join(net_conds)})")
            params.extend(networks)
        if node_types:
            placeholders = ", ".join(["?"] * len(node_types))
            conditions.append(f"node_type IN ({placeholders})")
            params.extend(node_types)

        where = " AND ".join(conditions)

        # COALESCE picks the best date: type-specific property date, then created_at
        best_date_expr = """COALESCE(
            CASE node_type
                WHEN 'EVENT' THEN json_extract_string(properties, '$.event_date')
                WHEN 'DECISION' THEN json_extract_string(properties, '$.decision_date')
                WHEN 'COMMITMENT' THEN json_extract_string(properties, '$.due_date')
                ELSE NULL
            END,
            CAST(created_at AS VARCHAR)
        )"""

        # Apply date range filter on the best date
        date_conditions = []
        if start:
            date_conditions.append(f"{best_date_expr} >= ?")
            params.append(start)
        if end:
            date_conditions.append(f"{best_date_expr} <= ?")
            params.append(end)

        if date_conditions:
            where += " AND " + " AND ".join(date_conditions)

        rows = self._conn.execute(
            f"""SELECT id, node_type, title, content, properties, networks,
                       confidence, created_at,
                       {best_date_expr} AS effective_date
                FROM nodes WHERE {where}
                ORDER BY effective_date ASC LIMIT ?""",
            params + [limit],
        ).fetchall()
        cols = ["id", "node_type", "title", "content", "properties", "networks",
                "confidence", "created_at", "effective_date"]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            d["properties"] = parse_properties(d["properties"])
            result.append(d)
        return result

    def get_temporal_neighbors_directed(
        self, node_id: str, direction: str = "both", edge_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Get temporal neighbors with direction awareness.

        Args:
            node_id: The node to find neighbors for.
            direction: "forward" (outgoing edges from this node),
                       "backward" (incoming edges to this node), or "both".
            edge_types: Edge types to filter on.
        """
        temporal_types = edge_types or ["PRECEDED_BY", "TRIGGERED", "EVOLVED_INTO", "CONCURRENT_WITH"]
        placeholders = ", ".join(["?"] * len(temporal_types))

        if direction == "forward":
            # Edges where this node is the source
            query = f"""SELECT e.id as edge_id, e.edge_type, e.source_id, e.target_id,
                               n.id as node_id, n.node_type, n.title, n.created_at
                        FROM edges e
                        JOIN nodes n ON e.target_id = n.id
                        WHERE e.source_id = ?
                          AND e.edge_type IN ({placeholders})
                          AND n.deleted = FALSE
                        ORDER BY n.created_at ASC"""
            params = [node_id] + temporal_types
        elif direction == "backward":
            # Edges where this node is the target
            query = f"""SELECT e.id as edge_id, e.edge_type, e.source_id, e.target_id,
                               n.id as node_id, n.node_type, n.title, n.created_at
                        FROM edges e
                        JOIN nodes n ON e.source_id = n.id
                        WHERE e.target_id = ?
                          AND e.edge_type IN ({placeholders})
                          AND n.deleted = FALSE
                        ORDER BY n.created_at ASC"""
            params = [node_id] + temporal_types
        else:
            # Both directions — use original symmetric query
            return self.get_temporal_neighbors(node_id, edge_types=temporal_types)

        rows = self._conn.execute(query, params).fetchall()
        cols = ["edge_id", "edge_type", "source_id", "target_id",
                "node_id", "node_type", "title", "created_at"]
        return [dict(zip(cols, row)) for row in rows]

    def get_patterns_for_node(self, node_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get patterns whose evidence list includes the given node ID."""
        try:
            rows = self._conn.execute(
                """SELECT id, pattern_type, description, evidence, confidence,
                          suggested_action, networks, status
                   FROM detected_patterns
                   WHERE status = 'active'
                     AND list_contains(
                         CAST(evidence AS VARCHAR[]),
                         ?
                     )
                   ORDER BY confidence DESC LIMIT ?""",
                [node_id, limit],
            ).fetchall()
            cols = ["id", "pattern_type", "description", "evidence", "confidence",
                    "suggested_action", "networks", "status"]
            result = []
            for row in rows:
                d = dict(zip(cols, row))
                if isinstance(d["evidence"], str):
                    d["evidence"] = json.loads(d["evidence"])
                if isinstance(d["networks"], str):
                    d["networks"] = json.loads(d["networks"])
                result.append(d)
            return result
        except Exception:
            return []

    def get_edges_between(self, source_id: str, target_id: str) -> list[Edge]:
        """Get all edges between two specific nodes (either direction)."""
        rows = self._conn.execute(
            """SELECT * FROM edges
               WHERE (source_id = ? AND target_id = ?)
                  OR (source_id = ? AND target_id = ?)""",
            [source_id, target_id, target_id, source_id],
        ).fetchall()
        return [self._row_to_edge(row) for row in rows]

    # ---- Row mappers ----

    def _row_to_capture(self, row: tuple) -> Capture:
        cols = ["id", "modality", "raw_content", "processed_content",
                "content_hash", "language", "metadata", "created_at"]
        data = dict(zip(cols, row))
        if isinstance(data["metadata"], str):
            data["metadata"] = json.loads(data["metadata"])
        elif data["metadata"] is None:
            data["metadata"] = {}
        return Capture(**data)

    def _row_to_node(self, row: tuple) -> BaseNode:
        cols = [
            "id", "node_type", "title", "content", "content_hash",
            "properties", "confidence", "networks", "human_approved",
            "proposed_by", "source_capture_id", "access_count",
            "last_accessed", "decay_score", "review_date", "tags",
            "created_at", "updated_at", "deleted",
        ]
        data = dict(zip(cols, row))
        data.pop("deleted", None)

        # Parse JSON properties
        if isinstance(data["properties"], str):
            data["properties"] = json.loads(data["properties"])
        elif data["properties"] is None:
            data["properties"] = {}

        # Convert networks from list of strings to list of enums
        if data["networks"]:
            data["networks"] = [NetworkType(n) for n in data["networks"]]
        else:
            data["networks"] = []

        if data["tags"] is None:
            data["tags"] = []

        # Ensure proposed_by is never None (model expects str)
        if data.get("proposed_by") is None:
            data["proposed_by"] = ""

        # Use the appropriate typed model
        node_type = NodeType(data["node_type"])
        model_cls = NODE_TYPE_MODEL_MAP.get(node_type, BaseNode)
        return model_cls(**data)

    # ── Pattern-detection helpers ─────────────────────────────────

    def get_nodes_by_type_with_properties(self, node_type: str, limit: int = 200) -> list[dict[str, Any]]:
        """Return non-deleted nodes of a type with parsed properties."""
        try:
            rows = self._conn.execute(
                """SELECT id, title, content, properties, networks, created_at, updated_at
                   FROM nodes
                   WHERE deleted = FALSE AND node_type = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                [node_type, limit],
            ).fetchall()
            results = []
            for r in rows:
                props = r[3]
                if isinstance(props, str):
                    props = json.loads(props)
                elif props is None:
                    props = {}
                networks = r[4] if r[4] else []
                results.append({
                    "id": r[0],
                    "title": r[1],
                    "content": r[2] or "",
                    "properties": props,
                    "networks": networks,
                    "created_at": r[5],
                    "updated_at": r[6],
                })
            return results
        except Exception:
            logger.warning("get_nodes_by_type_with_properties(%s) failed", node_type, exc_info=True)
            return []

    def get_active_goals_with_edges(self) -> list[dict[str, Any]]:
        """Return active goals with their connected commitment/project edge counts."""
        try:
            rows = self._conn.execute(
                """SELECT
                       g.id, g.title, g.properties, g.networks, g.created_at, g.updated_at,
                       (SELECT COUNT(*) FROM edges e
                        WHERE (e.source_id = g.id OR e.target_id = g.id)
                        AND e.edge_type IN ('SUBTASK_OF', 'CONTAINS', 'SUPPORTS', 'RELATES_TO')
                       ) AS edge_count
                   FROM nodes g
                   WHERE g.deleted = FALSE
                     AND g.node_type = 'GOAL'
                     AND json_extract_string(g.properties, '$.status') = 'active'
                   ORDER BY g.created_at DESC
                   LIMIT 200""",
            ).fetchall()
            results = []
            for r in rows:
                props = r[2]
                if isinstance(props, str):
                    props = json.loads(props)
                elif props is None:
                    props = {}
                networks = r[3] if r[3] else []
                results.append({
                    "id": r[0],
                    "title": r[1],
                    "properties": props,
                    "networks": networks,
                    "created_at": r[4],
                    "updated_at": r[5],
                    "edge_count": r[6],
                })
            return results
        except Exception:
            logger.warning("get_active_goals_with_edges failed", exc_info=True)
            return []

    def get_node_type_counts_by_network(self) -> dict[str, dict[str, int]]:
        """Return {network: {node_type: count}} for all networks."""
        result: dict[str, dict[str, int]] = {}
        try:
            for net in NetworkType:
                rows = self._conn.execute(
                    """SELECT node_type, COUNT(*) AS cnt
                       FROM nodes
                       WHERE deleted = FALSE AND list_contains(networks, ?)
                       GROUP BY node_type""",
                    [net.value],
                ).fetchall()
                if rows:
                    result[net.value] = {ntype: cnt for ntype, cnt in rows}
            return result
        except Exception:
            logger.warning("get_node_type_counts_by_network failed", exc_info=True)
            return {}

    def get_edge_type_summary(self, node_id: str) -> list[dict[str, Any]]:
        """Edge type counts grouped by type and direction for pre-expansion preview."""
        rows = self._conn.execute(
            """SELECT edge_type,
                      CASE WHEN source_id = ? THEN 'outgoing' ELSE 'incoming' END as direction,
                      COUNT(*) as count
               FROM edges WHERE source_id = ? OR target_id = ?
               GROUP BY edge_type, direction ORDER BY count DESC""",
            [node_id, node_id, node_id],
        ).fetchall()
        return [{"edge_type": r[0], "direction": r[1], "count": r[2]} for r in rows]

    # ── People Intelligence queries ────────────────────────────

    def get_all_people_with_stats(
        self,
        sort_by: str = "title",
        order: str = "asc",
        limit: int = 20,
        offset: int = 0,
        network_filter: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return PERSON nodes (excluding 'You') with connection counts and metadata.

        Returns ``(rows, total_count)`` for pagination.
        """
        try:
            net_clause = ""
            params: list[Any] = [YOU_NODE_ID]
            if network_filter:
                net_clause = "AND list_contains(n.networks, ?)"
                params.append(network_filter)

            allowed_sort = {
                "title": "n.title",
                "connections": "connection_count",
                "last_activity": "last_interaction",
                "decay": "n.decay_score",
                "confidence": "n.confidence",
            }
            sort_col = allowed_sort.get(sort_by, "n.title")
            order_dir = "DESC" if order.lower() == "desc" else "ASC"

            # Total count
            total = self._conn.execute(
                f"""SELECT COUNT(*) FROM nodes n
                    WHERE n.deleted = FALSE AND n.node_type = 'PERSON'
                    AND n.id != ? {net_clause}""",
                params,
            ).fetchone()[0]

            # Main query with edge counts
            rows = self._conn.execute(
                f"""WITH edge_counts AS (
                        SELECT nid, COUNT(*) AS cnt FROM (
                            SELECT source_id AS nid FROM edges
                            UNION ALL
                            SELECT target_id AS nid FROM edges
                        ) GROUP BY nid
                    )
                    SELECT
                        n.id, n.title, n.content, n.properties, n.networks,
                        n.confidence, n.decay_score, n.created_at, n.updated_at,
                        COALESCE(ec.cnt, 0) AS connection_count,
                        n.last_accessed AS last_interaction
                    FROM nodes n
                    LEFT JOIN edge_counts ec ON ec.nid = n.id
                    WHERE n.deleted = FALSE AND n.node_type = 'PERSON'
                    AND n.id != ? {net_clause}
                    ORDER BY {sort_col} {order_dir}
                    LIMIT ? OFFSET ?""",
                params + [limit, offset],
            ).fetchall()

            cols = [
                "id", "title", "content", "properties", "networks",
                "confidence", "decay_score", "created_at", "updated_at",
                "connection_count", "last_interaction",
            ]
            results = []
            for r in rows:
                d = dict(zip(cols, r))
                props = d["properties"]
                if isinstance(props, str):
                    props = json.loads(props)
                elif props is None:
                    props = {}
                d["properties"] = props
                d["role"] = props.get("role", "")
                d["organization"] = props.get("organization", "")
                d["relationship_to_user"] = props.get("relationship_to_user", "")
                d["networks"] = d["networks"] if d["networks"] else []
                results.append(d)

            return results, total
        except Exception:
            logger.warning("get_all_people_with_stats failed", exc_info=True)
            return [], 0

    def get_person_edges_with_nodes(self, person_id: str) -> list[dict[str, Any]]:
        """Return all edges touching a person with the connected node's basic info.

        Each result includes direction ('outgoing'/'incoming') and avoids N+1.
        """
        try:
            rows = self._conn.execute(
                """SELECT
                       e.id AS edge_id,
                       e.source_id, e.target_id,
                       e.edge_type, e.edge_category,
                       e.confidence AS edge_confidence,
                       e.weight AS edge_weight,
                       e.bidirectional,
                       e.created_at AS edge_created,
                       e.updated_at AS edge_updated,
                       CASE WHEN e.source_id = ? THEN 'outgoing' ELSE 'incoming' END AS direction,
                       -- Connected node info
                       cn.id AS node_id,
                       cn.node_type, cn.title AS node_title,
                       cn.content AS node_content,
                       cn.networks AS node_networks,
                       cn.confidence AS node_confidence,
                       cn.decay_score AS node_decay
                   FROM edges e
                   JOIN nodes cn
                       ON cn.id = CASE WHEN e.source_id = ? THEN e.target_id ELSE e.source_id END
                       AND cn.deleted = FALSE
                   WHERE e.source_id = ? OR e.target_id = ?""",
                [person_id, person_id, person_id, person_id],
            ).fetchall()

            cols = [
                "edge_id", "source_id", "target_id", "edge_type", "edge_category",
                "edge_confidence", "edge_weight", "bidirectional",
                "edge_created", "edge_updated", "direction",
                "node_id", "node_type", "node_title", "node_content",
                "node_networks", "node_confidence", "node_decay",
            ]
            return [dict(zip(cols, r)) for r in rows]
        except Exception:
            logger.warning("get_person_edges_with_nodes(%s) failed", person_id, exc_info=True)
            return []

    def get_people_stats(self) -> dict[str, Any]:
        """Aggregate people statistics for the intelligence dashboard."""
        try:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE deleted = FALSE AND node_type = 'PERSON' AND id != ?",
                [YOU_NODE_ID],
            ).fetchone()[0]

            # Network distribution
            net_dist: dict[str, int] = {}
            for net in NetworkType:
                cnt = self._conn.execute(
                    """SELECT COUNT(*) FROM nodes
                       WHERE deleted = FALSE AND node_type = 'PERSON'
                       AND id != ? AND list_contains(networks, ?)""",
                    [YOU_NODE_ID, net.value],
                ).fetchone()[0]
                if cnt > 0:
                    net_dist[net.value] = cnt

            # Most connected (top 5)
            most_connected = self._conn.execute(
                """WITH person_edges AS (
                       SELECT nid, COUNT(*) AS cnt FROM (
                           SELECT source_id AS nid FROM edges
                           UNION ALL
                           SELECT target_id AS nid FROM edges
                       ) GROUP BY nid
                   )
                   SELECT n.id, n.title, COALESCE(pe.cnt, 0) AS conns
                   FROM nodes n
                   LEFT JOIN person_edges pe ON pe.nid = n.id
                   WHERE n.deleted = FALSE AND n.node_type = 'PERSON' AND n.id != ?
                   ORDER BY conns DESC LIMIT 5""",
                [YOU_NODE_ID],
            ).fetchall()

            # Most recent (top 5)
            most_recent = self._conn.execute(
                """SELECT id, title, updated_at
                   FROM nodes
                   WHERE deleted = FALSE AND node_type = 'PERSON' AND id != ?
                   ORDER BY updated_at DESC LIMIT 5""",
                [YOU_NODE_ID],
            ).fetchall()

            # Average connections per person
            avg_conns = self._conn.execute(
                """WITH person_edges AS (
                       SELECT nid, COUNT(*) AS cnt FROM (
                           SELECT source_id AS nid FROM edges
                           UNION ALL
                           SELECT target_id AS nid FROM edges
                       ) GROUP BY nid
                   )
                   SELECT AVG(COALESCE(pe.cnt, 0))
                   FROM nodes n
                   LEFT JOIN person_edges pe ON pe.nid = n.id
                   WHERE n.deleted = FALSE AND n.node_type = 'PERSON' AND n.id != ?""",
                [YOU_NODE_ID],
            ).fetchone()[0] or 0.0

            # Edge type distribution for people edges
            edge_type_dist = self._conn.execute(
                """SELECT e.edge_type, COUNT(*) AS cnt
                   FROM edges e
                   JOIN nodes n ON (n.id = e.source_id OR n.id = e.target_id)
                       AND n.node_type = 'PERSON' AND n.deleted = FALSE AND n.id != ?
                   GROUP BY e.edge_type ORDER BY cnt DESC""",
                [YOU_NODE_ID],
            ).fetchall()

            # Disconnected count
            disconnected = self._conn.execute(
                """SELECT COUNT(*) FROM nodes n
                   WHERE n.deleted = FALSE AND n.node_type = 'PERSON' AND n.id != ?
                   AND NOT EXISTS (
                       SELECT 1 FROM edges e
                       WHERE e.source_id = n.id OR e.target_id = n.id
                   )""",
                [YOU_NODE_ID],
            ).fetchone()[0]

            return {
                "total_people": total,
                "network_distribution": net_dist,
                "most_connected": [
                    {"id": r[0], "title": r[1], "connections": r[2]}
                    for r in most_connected
                ],
                "most_recent": [
                    {"id": r[0], "title": r[1], "updated_at": r[2]}
                    for r in most_recent
                ],
                "avg_connections": round(float(avg_conns), 1),
                "edge_type_distribution": [
                    {"edge_type": r[0], "count": r[1]}
                    for r in edge_type_dist
                ],
                "disconnected_count": disconnected,
            }
        except Exception:
            logger.warning("get_people_stats failed", exc_info=True)
            return {"total_people": 0, "network_distribution": {}, "most_connected": [],
                    "most_recent": [], "avg_connections": 0.0, "edge_type_distribution": [],
                    "disconnected_count": 0}

    def get_strongest_person_ties(self, limit: int = 5) -> list[dict[str, Any]]:
        """Return the strongest person-to-person edges by weight and confidence."""
        try:
            rows = self._conn.execute(
                """SELECT e.source_id, e.target_id, e.edge_type,
                          e.weight, e.confidence, e.updated_at,
                          s.title AS source_title, t.title AS target_title
                   FROM edges e
                   JOIN nodes s ON s.id = e.source_id AND s.node_type = 'PERSON' AND s.deleted = FALSE
                   JOIN nodes t ON t.id = e.target_id AND t.node_type = 'PERSON' AND t.deleted = FALSE
                   ORDER BY e.weight DESC, e.confidence DESC
                   LIMIT ?""",
                [limit],
            ).fetchall()
            return [
                {
                    "source_id": r[0], "target_id": r[1], "edge_type": r[2],
                    "weight": r[3], "confidence": r[4], "updated_at": r[5],
                    "source_title": r[6], "target_title": r[7],
                }
                for r in rows
            ]
        except Exception:
            logger.warning("get_strongest_person_ties failed", exc_info=True)
            return []

    def get_mutual_connections(self, person_a_id: str, person_b_id: str) -> list[dict[str, Any]]:
        """Find nodes connected to both persons with edge context for each side."""
        try:
            rows = self._conn.execute(
                """WITH a_neighbors AS (
                       SELECT
                           CASE WHEN e.source_id = ? THEN e.target_id ELSE e.source_id END AS nid,
                           e.edge_type AS a_edge_type,
                           e.weight AS a_weight
                       FROM edges e
                       WHERE e.source_id = ? OR e.target_id = ?
                   ),
                   b_neighbors AS (
                       SELECT
                           CASE WHEN e.source_id = ? THEN e.target_id ELSE e.source_id END AS nid,
                           e.edge_type AS b_edge_type,
                           e.weight AS b_weight
                       FROM edges e
                       WHERE e.source_id = ? OR e.target_id = ?
                   )
                   SELECT
                       a.nid, n.title, n.node_type, n.networks,
                       a.a_edge_type, a.a_weight,
                       b.b_edge_type, b.b_weight
                   FROM a_neighbors a
                   JOIN b_neighbors b ON a.nid = b.nid
                   JOIN nodes n ON n.id = a.nid AND n.deleted = FALSE
                   WHERE a.nid != ? AND a.nid != ?""",
                [person_a_id, person_a_id, person_a_id,
                 person_b_id, person_b_id, person_b_id,
                 person_a_id, person_b_id],
            ).fetchall()

            results = []
            seen = set()
            for r in rows:
                nid = r[0]
                if nid in seen:
                    continue
                seen.add(nid)
                results.append({
                    "node_id": nid,
                    "title": r[1],
                    "node_type": r[2],
                    "networks": r[3] if r[3] else [],
                    "edge_to_a": {"edge_type": r[4], "weight": r[5]},
                    "edge_to_b": {"edge_type": r[6], "weight": r[7]},
                })
            return results
        except Exception:
            logger.warning("get_mutual_connections failed", exc_info=True)
            return []

    def _row_to_edge(self, row: tuple) -> Edge:
        cols = [
            "id", "source_id", "target_id", "edge_type", "edge_category",
            "properties", "confidence", "weight", "bidirectional",
            "created_at", "updated_at",
        ]
        data = dict(zip(cols, row))
        if isinstance(data["properties"], str):
            data["properties"] = json.loads(data["properties"])
        elif data["properties"] is None:
            data["properties"] = {}
        data["edge_type"] = EdgeType(data["edge_type"])
        data["edge_category"] = EdgeCategory(data["edge_category"])
        return Edge(**data)
