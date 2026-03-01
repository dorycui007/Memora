"""Tests for vector store — LanceDB embedding upsert and search."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from memora.vector.store import VectorStore, SearchResult


@pytest.fixture
def vector_store(tmp_path: Path) -> VectorStore:
    return VectorStore(db_path=tmp_path / "test_vectors")


def _fake_vector(seed: float = 0.0) -> list[float]:
    """Generate a deterministic 1024-dim vector for testing."""
    import math
    return [math.sin(seed + i * 0.01) for i in range(1024)]


class TestVectorStoreUpsert:
    def test_upsert_and_count(self, vector_store: VectorStore):
        vector_store.upsert_embedding(
            node_id="node-1",
            content="Test node content",
            node_type="PERSON",
            networks=["SOCIAL"],
            vector=_fake_vector(1.0),
        )
        # Should have 1 row
        count = vector_store._table.count_rows()
        assert count == 1

    def test_upsert_replaces_existing(self, vector_store: VectorStore):
        vector_store.upsert_embedding(
            node_id="node-1",
            content="Original content",
            node_type="PERSON",
            networks=["SOCIAL"],
            vector=_fake_vector(1.0),
        )
        vector_store.upsert_embedding(
            node_id="node-1",
            content="Updated content",
            node_type="PERSON",
            networks=["SOCIAL", "PROFESSIONAL"],
            vector=_fake_vector(2.0),
        )
        count = vector_store._table.count_rows()
        assert count == 1

    def test_delete_embedding(self, vector_store: VectorStore):
        vector_store.upsert_embedding(
            node_id="node-1",
            content="Test",
            node_type="NOTE",
            networks=["ACADEMIC"],
            vector=_fake_vector(1.0),
        )
        vector_store.delete_embedding("node-1")
        count = vector_store._table.count_rows()
        assert count == 0


class TestVectorStoreSearch:
    def _populate(self, vs: VectorStore):
        """Insert several test embeddings."""
        vs.upsert_embedding("p1", "Alice is an engineer", "PERSON", ["PROFESSIONAL"], _fake_vector(1.0))
        vs.upsert_embedding("p2", "Bob is a designer", "PERSON", ["PROFESSIONAL"], _fake_vector(1.1))
        vs.upsert_embedding("e1", "Team meeting about project", "EVENT", ["PROFESSIONAL"], _fake_vector(2.0))
        vs.upsert_embedding("n1", "Graph theory basics", "CONCEPT", ["ACADEMIC"], _fake_vector(3.0))

    def test_dense_search_returns_results(self, vector_store: VectorStore):
        self._populate(vector_store)
        results = vector_store.dense_search(
            query_vector=_fake_vector(1.05),
            top_k=3,
        )
        assert len(results) > 0
        assert all(isinstance(r, SearchResult) for r in results)

    def test_dense_search_similarity_order(self, vector_store: VectorStore):
        self._populate(vector_store)
        # Query close to person vectors (seed 1.0-1.1)
        results = vector_store.dense_search(
            query_vector=_fake_vector(1.0),
            top_k=4,
        )
        assert len(results) >= 2
        # Scores should be descending
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_filtered_search(self, vector_store: VectorStore):
        self._populate(vector_store)
        results = vector_store.filtered_search(
            query_vector=_fake_vector(1.0),
            node_type="PERSON",
            top_k=10,
        )
        assert all(r.node_type == "PERSON" for r in results)

    def test_search_result_to_dict(self):
        sr = SearchResult(
            node_id="n1", content="test", node_type="NOTE",
            networks=["ACADEMIC"], score=0.95,
        )
        d = sr.to_dict()
        assert d["node_id"] == "n1"
        assert d["score"] == 0.95
