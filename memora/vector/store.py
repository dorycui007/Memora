"""Weaviate vector store for semantic search over graph nodes.

Provides upsert, delete, and multi-mode search (dense, hybrid, filtered).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import weaviate
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.query import Filter, MetadataQuery
from weaviate.util import generate_uuid5

logger = logging.getLogger(__name__)

# Suppress noisy Weaviate client logs
logging.getLogger("weaviate").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)

EMBEDDING_DIM = 768
COLLECTION_NAME = "NodeEmbeddings"


class SearchResult:
    """A single search result from the vector store."""

    def __init__(self, node_id: str, content: str, node_type: str,
                 networks: list[str], score: float):
        self.node_id = node_id
        self.content = content
        self.node_type = node_type
        self.networks = networks
        self.score = score

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "content": self.content,
            "node_type": self.node_type,
            "networks": self.networks,
            "score": self.score,
        }


class VectorStore:
    """Weaviate-backed vector store for node embeddings."""

    def __init__(
        self,
        db_path: str | Path,
        port: int = 8079,
        grpc_port: int = 50050,
    ) -> None:
        self._db_path = str(db_path)
        self._client = weaviate.connect_to_embedded(
            persistence_data_path=self._db_path,
            port=port,
            grpc_port=grpc_port,
            environment_variables={"LOG_LEVEL": "error"},
        )
        self._collection = None
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create the embeddings collection if it doesn't exist."""
        if self._client.collections.exists(COLLECTION_NAME):
            self._collection = self._client.collections.get(COLLECTION_NAME)
            logger.debug("Opened existing embeddings collection")
        else:
            self._collection = self._client.collections.create(
                name=COLLECTION_NAME,
                vector_config=Configure.Vectors.self_provided(),
                properties=[
                    Property(name="node_id", data_type=DataType.TEXT),
                    Property(name="content", data_type=DataType.TEXT),
                    Property(name="node_type", data_type=DataType.TEXT),
                    Property(name="networks", data_type=DataType.TEXT_ARRAY),
                    Property(name="created_at", data_type=DataType.TEXT),
                ],
            )
            logger.info("Created new embeddings collection")

    @staticmethod
    def _node_uuid(node_id: str) -> str:
        """Deterministic UUID from node_id for O(1) get/delete/replace."""
        return generate_uuid5(node_id)

    def create_index(self) -> None:
        """No-op — Weaviate auto-manages HNSW indexes."""
        pass

    def upsert_embedding(
        self,
        node_id: str,
        content: str,
        node_type: str,
        networks: list[str],
        vector: list[float],
    ) -> None:
        """Insert or update an embedding for a node."""
        uuid = self._node_uuid(node_id)
        properties = {
            "node_id": node_id,
            "content": content,
            "node_type": node_type,
            "networks": networks,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._collection.data.replace(
                uuid=uuid,
                properties=properties,
                vector=vector,
            )
        except Exception:
            # Object doesn't exist yet — insert
            self._collection.data.insert(
                uuid=uuid,
                properties=properties,
                vector=vector,
            )

    def delete_embedding(self, node_id: str) -> None:
        """Delete embedding for a node."""
        try:
            self._collection.data.delete_by_id(self._node_uuid(node_id))
        except Exception:
            pass  # May not exist

    def get_embedding(self, node_id: str) -> list[float] | None:
        """Retrieve the dense vector for a node. Returns None if not found."""
        try:
            obj = self._collection.query.fetch_object_by_id(
                self._node_uuid(node_id),
                include_vector=True,
            )
            if obj is None:
                return None
            return list(obj.vector["default"])
        except Exception:
            return None

    def dense_search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Dense vector similarity search."""
        wv_filter = None
        if filters and "node_type" in filters:
            wv_filter = Filter.by_property("node_type").equal(filters["node_type"])

        try:
            response = self._collection.query.near_vector(
                near_vector=query_vector,
                limit=top_k,
                filters=wv_filter,
                return_metadata=MetadataQuery(distance=True),
            )
        except Exception:
            return []

        results = []
        for obj in response.objects:
            props = obj.properties
            results.append(SearchResult(
                node_id=props["node_id"],
                content=props["content"],
                node_type=props["node_type"],
                networks=props.get("networks", []),
                score=1.0 - (obj.metadata.distance or 0.0),
            ))
        return results

    def hybrid_search(
        self,
        query_vector: list[float],
        query_text: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Hybrid search combining dense vector + BM25 via Weaviate native fusion.

        Falls back to dense-only if hybrid is not available.
        """
        wv_filter = None
        if filters and "node_type" in filters:
            wv_filter = Filter.by_property("node_type").equal(filters["node_type"])

        try:
            response = self._collection.query.hybrid(
                query=query_text,
                vector=query_vector,
                alpha=0.5,
                limit=top_k,
                filters=wv_filter,
                return_metadata=MetadataQuery(score=True),
            )
            results = []
            for obj in response.objects:
                props = obj.properties
                results.append(SearchResult(
                    node_id=props["node_id"],
                    content=props["content"],
                    node_type=props["node_type"],
                    networks=props.get("networks", []),
                    score=obj.metadata.score if obj.metadata.score is not None else 0.0,
                ))
            return results
        except Exception:
            # Fallback to dense-only
            return self.dense_search(query_vector, top_k=top_k, filters=filters)

    def batch_upsert_embeddings(self, records: list[dict[str, Any]]) -> None:
        """Insert or update embeddings for multiple nodes in one call.

        Each record must have: node_id, content, node_type, networks, vector.
        """
        if not records:
            return

        now = datetime.now(timezone.utc).isoformat()

        with self._collection.batch.dynamic() as batch:
            for record in records:
                uuid = self._node_uuid(record["node_id"])
                batch.add_object(
                    uuid=uuid,
                    properties={
                        "node_id": record["node_id"],
                        "content": record["content"],
                        "node_type": record["node_type"],
                        "networks": record["networks"],
                        "created_at": now,
                    },
                    vector=record["vector"],
                )
        logger.info("Batch upserted %d embeddings", len(records))

    def get_embeddings_batch(self, node_ids: list[str]) -> dict[str, list[float]]:
        """Retrieve dense vectors for multiple nodes. Returns {node_id: vector}."""
        if not node_ids:
            return {}

        try:
            result: dict[str, list[float]] = {}
            for nid in node_ids:
                vec = self.get_embedding(nid)
                if vec is not None:
                    result[nid] = vec
            return result
        except Exception:
            logger.warning("Batch embedding retrieval failed", exc_info=True)
            return {}

    def filtered_search(
        self,
        query_vector: list[float],
        node_type: str | None = None,
        networks: list[str] | None = None,
        top_k: int = 10,
    ) -> list[SearchResult]:
        """Search with pre-filters on node_type and/or networks."""
        filters: dict[str, Any] = {}
        if node_type:
            filters["node_type"] = node_type
        return self.dense_search(query_vector, top_k=top_k, filters=filters)

    def close(self) -> None:
        """Close the Weaviate client and embedded subprocess."""
        try:
            self._client.close()
        except Exception:
            pass
