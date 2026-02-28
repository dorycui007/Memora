"""Graph repository — DuckDB-backed storage for the knowledge graph.

Provides CRUD operations for nodes, edges, captures, and proposals,
with atomic transaction support for committing graph proposals.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
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
)

logger = logging.getLogger(__name__)

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
            [datetime.utcnow().isoformat(), str(node_id)],
        )
        return self._row_to_node(row)

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
        params.append(datetime.utcnow().isoformat())
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
            [datetime.utcnow().isoformat(), str(node_id)],
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
        """Get the subgraph within N hops of a node."""
        visited_nodes: set[str] = set()
        frontier: set[str] = {str(node_id)}
        all_edges: list[Edge] = []

        for _ in range(hops):
            next_frontier: set[str] = set()
            for nid in frontier:
                if nid in visited_nodes:
                    continue
                visited_nodes.add(nid)
                edges = self.get_edges(UUID(nid))
                for edge in edges:
                    all_edges.append(edge)
                    src = str(edge.source_id)
                    tgt = str(edge.target_id)
                    if src not in visited_nodes:
                        next_frontier.add(src)
                    if tgt not in visited_nodes:
                        next_frontier.add(tgt)
            frontier = next_frontier

        # Also include the last frontier nodes
        visited_nodes.update(frontier)

        nodes = []
        for nid in visited_nodes:
            node = self.get_node(UUID(nid))
            if node:
                nodes.append(node)

        # Deduplicate edges
        seen_edge_ids: set[str] = set()
        unique_edges = []
        for e in all_edges:
            eid = str(e.id)
            if eid not in seen_edge_ids:
                seen_edge_ids.add(eid)
                unique_edges.append(e)

        return Subgraph(nodes=nodes, edges=unique_edges)

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
                datetime.utcnow().isoformat(),
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
            [status.value, datetime.utcnow().isoformat(), reviewer, str(proposal_id)],
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
                now = datetime.utcnow().isoformat()

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
                        v = json.dumps(v)
                    set_parts.append(f"{k} = ?")
                    vals.append(v)
                if set_parts:
                    set_parts.append("updated_at = ?")
                    vals.append(datetime.utcnow().isoformat())
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
                now = datetime.utcnow().isoformat()

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
                    datetime.utcnow().isoformat(),
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
                   ORDER BY computed_at DESC
                   LIMIT 7"""
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
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
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
