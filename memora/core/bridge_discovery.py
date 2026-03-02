"""Bridge Discovery — detect cross-network connections via embedding similarity.

Finds nodes in different networks that are semantically similar,
indicating potential cross-network insights or connections.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
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
            try:
                if self._repo.bridge_exists(str(node.id), result.node_id):
                    continue
            except Exception:
                continue

            bridge = {
                "id": str(uuid4()),
                "source_node_id": str(node.id),
                "target_node_id": result.node_id,
                "source_network": source_network,
                "target_network": target_network,
                "similarity": result.score,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                self._repo.store_bridge(bridge)
            except Exception:
                logger.warning("Failed to store bridge", exc_info=True)
            bridges.append(bridge)

        if bridges:
            logger.info(
                "Discovered %d bridges for node %s", len(bridges), node_id
            )

        return bridges

    def get_bridges(
        self,
        network: str | None = None,
        validated_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query discovered bridges."""
        return self._repo.query_bridges(
            network=network,
            validated_only=validated_only,
            limit=limit,
        )
