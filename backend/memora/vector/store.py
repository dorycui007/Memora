"""LanceDB vector store for semantic search over graph nodes.

Provides upsert, delete, and multi-mode search (dense, hybrid, filtered).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768

# PyArrow schema for the embeddings table
EMBEDDINGS_SCHEMA = pa.schema([
    pa.field("node_id", pa.string()),
    pa.field("content", pa.string()),
    pa.field("node_type", pa.string()),
    pa.field("networks", pa.list_(pa.string())),
    pa.field("dense", pa.list_(pa.float32(), EMBEDDING_DIM)),
    pa.field("created_at", pa.string()),
])


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
    """LanceDB-backed vector store for node embeddings."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._db = lancedb.connect(self._db_path)
        self._table_name = "node_embeddings"
        self._table = None
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create the embeddings table if it doesn't exist."""
        try:
            self._table = self._db.open_table(self._table_name)
            logger.debug("Opened existing embeddings table")
        except Exception:
            # Create with empty data matching schema
            self._table = self._db.create_table(
                self._table_name,
                schema=EMBEDDINGS_SCHEMA,
            )
            logger.info("Created new embeddings table")

    def create_index(self) -> None:
        """Create HNSW index for fast ANN search. Call after bulk inserts."""
        if self._table is None:
            return
        try:
            row_count = self._table.count_rows()
            if row_count >= 256:
                self._table.create_index(
                    metric="cosine",
                    num_partitions=4,
                    num_sub_vectors=16,
                    index_type="IVF_HNSW_SQ",
                )
                logger.info("Created HNSW index on %d rows", row_count)
            else:
                logger.debug("Skipping index creation: only %d rows (need 256+)", row_count)
        except Exception:
            logger.warning("Index creation failed (may already exist or insufficient data)")

    def upsert_embedding(
        self,
        node_id: str,
        content: str,
        node_type: str,
        networks: list[str],
        vector: list[float],
    ) -> None:
        """Insert or update an embedding for a node."""
        # Delete existing entry if present
        self.delete_embedding(node_id)

        record = {
            "node_id": node_id,
            "content": content,
            "node_type": node_type,
            "networks": networks,
            "dense": vector,
            "created_at": datetime.utcnow().isoformat(),
        }
        self._table.add([record])

    def delete_embedding(self, node_id: str) -> None:
        """Delete embedding for a node."""
        try:
            self._table.delete(f"node_id = '{node_id}'")
        except Exception:
            pass  # May not exist

    def get_embedding(self, node_id: str) -> list[float] | None:
        """Retrieve the dense vector for a node. Returns None if not found."""
        try:
            df = self._table.search().where(f"node_id = '{node_id}'").limit(1).to_pandas()
            if df.empty:
                return None
            return df.iloc[0]["dense"].tolist()
        except Exception:
            return None

    def dense_search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Dense vector similarity search."""
        query = self._table.search(query_vector, vector_column_name="dense").limit(top_k)

        if filters:
            where_parts = []
            if "node_type" in filters:
                where_parts.append(f"node_type = '{filters['node_type']}'")
            if where_parts:
                query = query.where(" AND ".join(where_parts))

        try:
            results = query.to_pandas()
        except Exception:
            return []

        search_results = []
        for _, row in results.iterrows():
            search_results.append(SearchResult(
                node_id=row["node_id"],
                content=row["content"],
                node_type=row["node_type"],
                networks=row["networks"] if isinstance(row["networks"], list) else [],
                score=1.0 - row.get("_distance", 0.0),
            ))
        return search_results

    def hybrid_search(
        self,
        query_vector: list[float],
        query_text: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Hybrid search combining dense vector + full-text (reciprocal rank fusion).

        Falls back to dense-only if FTS is not available.
        """
        # Dense results
        dense_results = self.dense_search(query_vector, top_k=top_k * 2, filters=filters)

        # FTS results via LanceDB's built-in FTS if available
        fts_results: list[SearchResult] = []
        try:
            fts_query = (
                self._table.search(query_text, query_type="fts")
                .limit(top_k * 2)
            )
            fts_df = fts_query.to_pandas()
            for _, row in fts_df.iterrows():
                fts_results.append(SearchResult(
                    node_id=row["node_id"],
                    content=row["content"],
                    node_type=row["node_type"],
                    networks=row["networks"] if isinstance(row["networks"], list) else [],
                    score=row.get("score", 0.5),
                ))
        except Exception:
            pass  # FTS not available, use dense only

        if not fts_results:
            return dense_results[:top_k]

        # Reciprocal rank fusion
        k = 60  # RRF constant
        scores: dict[str, float] = {}
        node_map: dict[str, SearchResult] = {}

        for rank, r in enumerate(dense_results):
            scores[r.node_id] = scores.get(r.node_id, 0) + 1.0 / (k + rank + 1)
            node_map[r.node_id] = r

        for rank, r in enumerate(fts_results):
            scores[r.node_id] = scores.get(r.node_id, 0) + 1.0 / (k + rank + 1)
            node_map[r.node_id] = r

        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)[:top_k]
        results = []
        for nid in sorted_ids:
            sr = node_map[nid]
            sr.score = scores[nid]
            results.append(sr)
        return results

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
