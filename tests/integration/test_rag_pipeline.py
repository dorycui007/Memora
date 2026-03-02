"""Integration tests for the RAG pipeline and search (Phase 4)."""

from __future__ import annotations

import re
import tempfile

import pytest
from unittest.mock import MagicMock, patch

from memora.graph.repository import GraphRepository
from memora.graph.models import (
    NetworkType,
    NodeType,
    PersonNode,
    EventNode,
)
from memora.agents.researcher import ResearcherAgent
from memora.vector.store import VectorStore, SearchResult, EMBEDDING_DIM


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo():
    """In-memory DuckDB repository for testing."""
    r = GraphRepository(db_path=None)
    yield r
    r.close()


@pytest.fixture(scope="module")
def vector_store(tmp_path_factory):
    """Weaviate-backed vector store in a temporary directory."""
    db_path = tmp_path_factory.mktemp("vectors") / "test_weaviate"
    vs = VectorStore(db_path=str(db_path), port=8081, grpc_port=50052)
    yield vs
    vs.close()


@pytest.fixture(autouse=True)
def _clear_vector_store(vector_store):
    """Delete and recreate collection between tests to ensure isolation."""
    from memora.vector.store import COLLECTION_NAME
    yield
    vector_store._client.collections.delete(COLLECTION_NAME)
    vector_store._ensure_collection()


def _random_vector(dim: int = EMBEDDING_DIM) -> list[float]:
    """Return a deterministic pseudo-random unit vector for testing."""
    import math
    # Simple deterministic vector based on index modulo
    raw = [(i % 7 - 3) * 0.1 for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


def _make_vector(seed: float, dim: int = EMBEDDING_DIM) -> list[float]:
    """Return a vector biased toward a particular direction for search tests."""
    import math
    raw = [seed + (i % 5) * 0.01 for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


# ---------------------------------------------------------------------------
# Vector search: dense
# ---------------------------------------------------------------------------


class TestVectorSearchBasic:
    """Test that dense_search returns results from the vector store."""

    def test_dense_search_returns_inserted_nodes(self, vector_store):
        """Upserting embeddings and searching should return them."""
        vec = _random_vector()
        vector_store.upsert_embedding(
            node_id="node-1",
            content="Coffee meeting with investor Sam",
            node_type="EVENT",
            networks=["VENTURES"],
            vector=vec,
        )
        vector_store.upsert_embedding(
            node_id="node-2",
            content="Dinner with family",
            node_type="EVENT",
            networks=["FAMILY"],
            vector=vec,
        )

        results = vector_store.dense_search(vec, top_k=5)
        assert len(results) == 2
        node_ids = {r.node_id for r in results}
        assert "node-1" in node_ids
        assert "node-2" in node_ids

    def test_dense_search_respects_top_k(self, vector_store):
        """top_k should limit the number of results returned."""
        vec = _random_vector()
        for i in range(10):
            vector_store.upsert_embedding(
                node_id=f"node-{i}",
                content=f"Content {i}",
                node_type="EVENT",
                networks=["SOCIAL"],
                vector=vec,
            )

        results = vector_store.dense_search(vec, top_k=3)
        assert len(results) == 3

    def test_dense_search_empty_store(self, vector_store):
        """Searching an empty store should return an empty list, not error."""
        vec = _random_vector()
        results = vector_store.dense_search(vec, top_k=5)
        assert results == []

    def test_dense_search_with_node_type_filter(self, vector_store):
        """Filtering by node_type should only return matching nodes."""
        vec = _random_vector()
        vector_store.upsert_embedding(
            node_id="person-1",
            content="Sam Chen",
            node_type="PERSON",
            networks=["VENTURES"],
            vector=vec,
        )
        vector_store.upsert_embedding(
            node_id="event-1",
            content="Coffee meeting",
            node_type="EVENT",
            networks=["VENTURES"],
            vector=vec,
        )

        results = vector_store.dense_search(
            vec, top_k=10, filters={"node_type": "PERSON"}
        )
        assert len(results) == 1
        assert results[0].node_id == "person-1"

    def test_search_result_has_score(self, vector_store):
        """Each search result should carry a similarity score."""
        vec = _random_vector()
        vector_store.upsert_embedding(
            node_id="node-x",
            content="Test content",
            node_type="EVENT",
            networks=["SOCIAL"],
            vector=vec,
        )

        results = vector_store.dense_search(vec, top_k=1)
        assert len(results) == 1
        assert isinstance(results[0].score, float)
        # Searching with the same vector should yield high similarity
        assert results[0].score > 0.9

    def test_search_result_to_dict(self, vector_store):
        """SearchResult.to_dict() should return proper dictionary."""
        vec = _random_vector()
        vector_store.upsert_embedding(
            node_id="dict-test",
            content="Dict test content",
            node_type="PERSON",
            networks=["SOCIAL", "VENTURES"],
            vector=vec,
        )

        results = vector_store.dense_search(vec, top_k=1)
        d = results[0].to_dict()
        assert d["node_id"] == "dict-test"
        assert d["content"] == "Dict test content"
        assert d["node_type"] == "PERSON"
        assert "score" in d

    def test_upsert_replaces_existing(self, vector_store):
        """Upserting the same node_id should replace, not duplicate."""
        vec = _random_vector()
        vector_store.upsert_embedding(
            node_id="dup-1",
            content="Original content",
            node_type="EVENT",
            networks=["SOCIAL"],
            vector=vec,
        )
        vector_store.upsert_embedding(
            node_id="dup-1",
            content="Updated content",
            node_type="EVENT",
            networks=["SOCIAL"],
            vector=vec,
        )

        results = vector_store.dense_search(vec, top_k=10)
        matching = [r for r in results if r.node_id == "dup-1"]
        assert len(matching) == 1
        assert matching[0].content == "Updated content"


# ---------------------------------------------------------------------------
# Hybrid search fallback
# ---------------------------------------------------------------------------


class TestHybridSearchFallback:
    """Test that hybrid search degrades gracefully when FTS is unavailable."""

    def test_hybrid_falls_back_to_dense(self, vector_store):
        """When FTS is not available, hybrid_search should return dense results."""
        vec = _random_vector()
        vector_store.upsert_embedding(
            node_id="hybrid-1",
            content="Quarterly board meeting notes",
            node_type="EVENT",
            networks=["VENTURES"],
            vector=vec,
        )
        vector_store.upsert_embedding(
            node_id="hybrid-2",
            content="Weekly team standup",
            node_type="EVENT",
            networks=["PROFESSIONAL"],
            vector=vec,
        )

        results = vector_store.hybrid_search(
            query_vector=vec,
            query_text="board meeting",
            top_k=5,
        )
        # Should still get results from the dense path
        assert len(results) >= 1
        node_ids = {r.node_id for r in results}
        assert "hybrid-1" in node_ids

    def test_hybrid_respects_top_k(self, vector_store):
        """Even in fallback mode, top_k should be respected."""
        vec = _random_vector()
        for i in range(10):
            vector_store.upsert_embedding(
                node_id=f"hk-{i}",
                content=f"Node content {i}",
                node_type="EVENT",
                networks=["SOCIAL"],
                vector=vec,
            )

        results = vector_store.hybrid_search(
            query_vector=vec,
            query_text="node content",
            top_k=4,
        )
        assert len(results) <= 4

    def test_hybrid_empty_store(self, vector_store):
        """Hybrid search on empty store should return empty list."""
        vec = _random_vector()
        results = vector_store.hybrid_search(
            query_vector=vec,
            query_text="anything",
            top_k=5,
        )
        assert results == []


# ---------------------------------------------------------------------------
# PII anonymization in the Researcher agent
# ---------------------------------------------------------------------------


class TestPIIAnonymization:
    """Test the ResearcherAgent's PII stripping before external queries."""

    @pytest.fixture
    def researcher(self):
        """ResearcherAgent with mocked Anthropic client."""
        with patch("memora.agents.researcher.openai.OpenAI"):
            agent = ResearcherAgent(api_key="fake-key")
        return agent

    def test_email_stripped(self, researcher):
        query = "Send a follow-up to sam@example.com about the deal"
        anon = researcher._anonymize_query(query)
        assert "sam@example.com" not in anon
        assert "@" not in anon

    def test_phone_stripped(self, researcher):
        query = "Call Sam at 415-555-1234 to discuss the pitch"
        anon = researcher._anonymize_query(query)
        assert "415-555-1234" not in anon

    def test_ssn_stripped(self, researcher):
        query = "My SSN is 123-45-6789 and I need tax advice"
        anon = researcher._anonymize_query(query)
        assert "123-45-6789" not in anon

    def test_dollar_amount_stripped(self, researcher):
        query = "The deal is worth $5,000,000 and closing soon"
        anon = researcher._anonymize_query(query)
        assert "$5,000,000" not in anon
        assert "a sum of money" in anon

    def test_date_stripped(self, researcher):
        query = "We signed the contract on January 15, 2025"
        anon = researcher._anonymize_query(query)
        assert "January 15, 2025" not in anon
        assert "recently" in anon

    def test_iso_date_stripped(self, researcher):
        query = "The meeting is scheduled for 2025-03-15"
        anon = researcher._anonymize_query(query)
        assert "2025-03-15" not in anon

    def test_names_from_context_stripped(self, researcher):
        """Names found in graph context should be replaced with 'someone'."""
        query = "What investments has Sam Chen made recently?"
        context = {
            "nodes": [
                {
                    "node_type": "PERSON",
                    "title": "Sam Chen",
                    "content": "Sam Chen",
                }
            ]
        }
        anon = researcher._anonymize_query(query, graph_context=context)
        assert "Sam Chen" not in anon
        assert "Sam" not in anon

    def test_clean_query_unchanged(self, researcher):
        """A query without PII should pass through mostly intact."""
        query = "What are best practices for startup fundraising?"
        anon = researcher._anonymize_query(query)
        assert "best practices" in anon
        assert "startup fundraising" in anon

    def test_multiple_pii_types(self, researcher):
        """Multiple PII types in a single query should all be stripped."""
        query = (
            "Email sam@startup.io at 650-555-9876 about the $2M deal "
            "we signed on March 1, 2025"
        )
        anon = researcher._anonymize_query(query)
        assert "sam@startup.io" not in anon
        assert "650-555-9876" not in anon
        assert "$2M" not in anon
        assert "March 1, 2025" not in anon

    def test_context_anonymization(self, researcher):
        """_anonymize_context should strip person content but keep node types."""
        context = {
            "nodes": [
                {
                    "node_type": "PERSON",
                    "title": "Sam Chen",
                    "content": "Sam Chen is an investor",
                    "networks": ["VENTURES"],
                },
                {
                    "node_type": "EVENT",
                    "title": "Board meeting",
                    "content": "Quarterly board meeting",
                    "networks": ["VENTURES"],
                },
            ],
            "stats": {"node_count": 42},
        }
        anon = researcher._anonymize_context(context)

        # Person nodes should not have content
        person_node = [n for n in anon["nodes"] if n["node_type"] == "PERSON"][0]
        assert "content_summary" not in person_node
        assert "Sam Chen" not in str(person_node)

        # Event nodes should have truncated content
        event_node = [n for n in anon["nodes"] if n["node_type"] == "EVENT"][0]
        assert "content_summary" in event_node

        # Stats should pass through
        assert anon["stats"]["node_count"] == 42


# ---------------------------------------------------------------------------
# Researcher response parsing
# ---------------------------------------------------------------------------


class TestResearcherParsing:
    """Test the Researcher's JSON extraction and response parsing."""

    @pytest.fixture
    def researcher(self):
        with patch("memora.agents.researcher.openai.OpenAI"):
            agent = ResearcherAgent(api_key="fake-key")
        return agent

    def test_parse_json_response(self, researcher):
        raw = '{"answer": "The sky is blue.", "confidence": 0.9, "sources": []}'
        result = researcher._parse_research_response(raw)
        assert result.answer == "The sky is blue."
        assert result.confidence == pytest.approx(0.9)

    def test_parse_json_in_code_block(self, researcher):
        raw = '```json\n{"answer": "42", "confidence": 0.75, "sources": []}\n```'
        result = researcher._parse_research_response(raw)
        assert result.answer == "42"

    def test_parse_plain_text_fallback(self, researcher):
        raw = "This is just plain text with no JSON."
        result = researcher._parse_research_response(raw)
        assert result.answer == raw

    def test_parse_sources(self, researcher):
        raw = (
            '{"answer": "Data found.", "confidence": 0.8, '
            '"sources": [{"url": "https://example.com", "title": "Example", '
            '"snippet": "A snippet", "source_type": "PRIMARY", "reliability_score": 0.9}]}'
        )
        result = researcher._parse_research_response(raw)
        assert len(result.sources) == 1
        assert result.sources[0].url == "https://example.com"
        assert result.sources[0].reliability_score == pytest.approx(0.9)
        assert result.sources[0].source_type == "PRIMARY"
