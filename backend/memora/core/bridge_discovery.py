"""Bridge Discovery — detect cross-network connections via embedding similarity.

Finds nodes in different networks that are semantically similar,
indicating potential cross-network insights or connections.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from memora.graph.repository import GraphRepository
from memora.vector.embeddings import EmbeddingEngine
from memora.vector.store import VectorStore

logger = logging.getLogger(__name__)


class BridgeDiscovery:
    """Detect cross-network connections via embedding similarity."""

    def __init__(
        self,
        repo: GraphRepository,
        vector_store: VectorStore,
        embedding_engine: EmbeddingEngine,
        similarity_threshold: float = 0.80,
    ) -> None:
        self._repo = repo
        self._vector_store = vector_store
        self._embedding_engine = embedding_engine
        self._similarity_threshold = similarity_threshold

    def discover_bridges_for_node(self, node_id: str) -> list[dict[str, Any]]:
        """Find nodes in OTHER networks semantically similar to this node.

        Returns list of discovered bridge dicts.
        """
        node = self._repo.get_node(UUID(node_id))
        if not node:
            return []

        node_networks = set(n.value for n in node.networks)
        if not node_networks:
            return []

        # Embed the node
        text = f"{node.title} {node.content}" if node.content else node.title
        try:
            embedding = self._embedding_engine.embed_text(text)
        except Exception:
            logger.warning("Failed to embed node %s for bridge discovery", node_id)
            return []

        # Search for similar nodes
        results = self._vector_store.dense_search(embedding["dense"], top_k=20)

        bridges = []
        for result in results:
            # Skip self
            if result.node_id == str(node.id):
                continue

            # Skip if below threshold
            if result.score < self._similarity_threshold:
                continue

            result_networks = set(result.networks) if result.networks else set()
            if not result_networks:
                continue

            # Only interested in cross-network matches
            if result_networks.issubset(node_networks):
                continue

            # Find the cross-network pair
            source_network = sorted(node_networks)[0]
            target_networks = result_networks - node_networks
            if not target_networks:
                continue
            target_network = sorted(target_networks)[0]

            # Check if bridge already exists
            if self._bridge_exists(str(node.id), result.node_id):
                continue

            bridge = {
                "source_node_id": str(node.id),
                "target_node_id": result.node_id,
                "source_network": source_network,
                "target_network": target_network,
                "similarity": result.score,
            }
            self._store_bridge(bridge)
            bridges.append(bridge)

        if bridges:
            logger.info(
                "Discovered %d bridges for node %s", len(bridges), node_id
            )

        return bridges

    def _bridge_exists(self, source_id: str, target_id: str) -> bool:
        """Check if a bridge between these two nodes already exists."""
        try:
            count = self._repo._conn.execute(
                """SELECT COUNT(*) FROM bridges
                   WHERE (source_node_id = ? AND target_node_id = ?)
                   OR (source_node_id = ? AND target_node_id = ?)""",
                [source_id, target_id, target_id, source_id],
            ).fetchone()[0]
            return count > 0
        except Exception:
            return False

    def _store_bridge(self, bridge: dict[str, Any]) -> None:
        """Store a discovered bridge in the bridges table."""
        try:
            self._repo._conn.execute(
                """INSERT INTO bridges
                   (id, source_node_id, target_node_id, source_network,
                    target_network, similarity, llm_validated, meaningful,
                    description, discovered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    str(uuid4()),
                    bridge["source_node_id"],
                    bridge["target_node_id"],
                    bridge["source_network"],
                    bridge["target_network"],
                    bridge["similarity"],
                    False,
                    None,
                    None,
                    datetime.utcnow().isoformat(),
                ],
            )
        except Exception:
            logger.warning("Failed to store bridge", exc_info=True)

    def get_bridges(
        self,
        network: str | None = None,
        validated_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query discovered bridges."""
        conditions = []
        params: list[Any] = []

        if network:
            conditions.append("(source_network = ? OR target_network = ?)")
            params.extend([network, network])

        if validated_only:
            conditions.append("llm_validated = TRUE AND meaningful = TRUE")

        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self._repo._conn.execute(
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
