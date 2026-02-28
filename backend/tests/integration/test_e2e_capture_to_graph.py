"""End-to-end tests: user input → OpenAI extraction → graph commit → nodes on relation graph.

Tests the full pipeline from user input through the extraction pipeline
(with mocked OpenAI) to verifying nodes and edges appear via the graph API.

Strategy: We drive the pipeline directly (bypassing asyncio.create_task)
then validate results through the FastAPI graph endpoints.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from memora.agents.archivist import ArchivistAgent
from memora.core.pipeline import ExtractionPipeline
from memora.graph.models import Capture
from memora.graph.repository import GraphRepository


# ── Mock OpenAI response builder ────────────────────────────────


def _make_openai_response(proposal_json: dict) -> MagicMock:
    """Build a mock OpenAI Responses API return value."""
    resp = MagicMock()
    resp.output_text = json.dumps(proposal_json)
    resp.usage = MagicMock(input_tokens=400, output_tokens=180)
    return resp


# ── Proposal factories ──────────────────────────────────────────


def _coffee_proposal() -> dict:
    """Standard proposal: person + event + commitment + 3 edges."""
    return {
        "confidence": 0.90,
        "nodes_to_create": [
            {
                "temp_id": "person_1",
                "node_type": "PERSON",
                "title": "Sam Chen",
                "content": "Investor contact met at Blue Bottle Coffee",
                "properties": {"name": "Sam Chen", "role": "Investor"},
                "confidence": 0.92,
                "networks": ["VENTURES", "SOCIAL"],
            },
            {
                "temp_id": "event_1",
                "node_type": "EVENT",
                "title": "Coffee with Sam",
                "content": "Discussed Series A investment opportunity",
                "properties": {
                    "location": "Blue Bottle Coffee",
                    "event_type": "meeting",
                    "participants": ["Sam Chen"],
                },
                "confidence": 0.88,
                "networks": ["VENTURES"],
            },
            {
                "temp_id": "commit_1",
                "node_type": "COMMITMENT",
                "title": "Send pitch deck to Sam",
                "content": "Promised to send updated pitch deck by Friday",
                "properties": {
                    "committed_by": "user",
                    "committed_to": "Sam Chen",
                    "status": "open",
                },
                "confidence": 0.91,
                "networks": ["VENTURES"],
            },
        ],
        "edges_to_create": [
            {
                "source_id": "person_1",
                "target_id": "event_1",
                "edge_type": "RELATED_TO",
                "edge_category": "ASSOCIATIVE",
                "confidence": 0.90,
            },
            {
                "source_id": "person_1",
                "target_id": "commit_1",
                "edge_type": "COMMITTED_TO",
                "edge_category": "PERSONAL",
                "confidence": 0.88,
            },
            {
                "source_id": "event_1",
                "target_id": "commit_1",
                "edge_type": "TRIGGERED",
                "edge_category": "TEMPORAL",
                "confidence": 0.85,
            },
        ],
        "nodes_to_update": [],
        "human_summary": "Coffee meeting with Sam Chen; committed to send pitch deck",
    }


def _idea_proposal() -> dict:
    """Single IDEA node, no edges."""
    return {
        "confidence": 0.87,
        "nodes_to_create": [
            {
                "temp_id": "idea_1",
                "node_type": "IDEA",
                "title": "AI-powered gardening assistant",
                "content": "An app that uses computer vision to identify plant diseases",
                "properties": {"domain": "agri-tech", "maturity": "seed"},
                "confidence": 0.87,
                "networks": ["VENTURES"],
            },
        ],
        "edges_to_create": [],
        "nodes_to_update": [],
        "human_summary": "New idea: AI gardening assistant",
    }


def _financial_proposal() -> dict:
    """Single FINANCIAL_ITEM node."""
    return {
        "confidence": 0.93,
        "nodes_to_create": [
            {
                "temp_id": "fin_1",
                "node_type": "FINANCIAL_ITEM",
                "title": "Monthly rent payment",
                "content": "Rent for apartment at 123 Main St",
                "properties": {
                    "amount": 2500.00,
                    "currency": "USD",
                    "direction": "outflow",
                    "category": "housing",
                    "recurring": True,
                    "frequency": "monthly",
                },
                "confidence": 0.95,
                "networks": ["FINANCIAL"],
            },
        ],
        "edges_to_create": [],
        "nodes_to_update": [],
        "human_summary": "Monthly rent $2,500",
    }


def _clarification_proposal() -> dict:
    """Triggers clarification (confidence=0.0, no nodes)."""
    return {
        "confidence": 0.0,
        "nodes_to_create": [],
        "edges_to_create": [],
        "nodes_to_update": [],
        "human_summary": "Could you clarify which project you are referring to?",
    }


def _low_confidence_proposal() -> dict:
    """Confidence below auto-approve threshold → DIGEST route."""
    return {
        "confidence": 0.55,
        "nodes_to_create": [
            {
                "temp_id": "note_1",
                "node_type": "NOTE",
                "title": "Something about a meeting",
                "content": "Unclear reference to a meeting next week",
                "properties": {"note_type": "observation"},
                "confidence": 0.55,
                "networks": ["PROFESSIONAL"],
            },
        ],
        "edges_to_create": [],
        "nodes_to_update": [],
        "human_summary": "Ambiguous note about a meeting",
    }


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def repo():
    """In-memory DuckDB graph repository."""
    r = GraphRepository(db_path=None)
    yield r
    r.close()


def _create_test_app(repo: GraphRepository) -> FastAPI:
    """Create a lightweight FastAPI app for testing (no lifespan/scheduler)."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _test_lifespan(app: FastAPI):
        # Wire test fixtures directly — no file DB, no scheduler
        app.state.repo = repo
        app.state.settings = MagicMock(
            openai_api_key="test-key-e2e",
            auto_approve_threshold=0.85,
        )
        app.state.vector_store = None
        app.state.embedding_engine = None
        app.state.pipeline = None
        app.state.orchestrator = None
        app.state.strategist = None
        app.state.scheduler = None
        yield
        # No shutdown needed for in-memory DB (fixture handles close)

    app = FastAPI(title="Memora Test", lifespan=_test_lifespan)

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    from memora.api.routes.captures import router as captures_router
    from memora.api.routes.graph import router as graph_router

    app.include_router(captures_router)
    app.include_router(graph_router)

    return app


@pytest.fixture
def app(repo):
    """FastAPI app wired to in-memory repo, no heavy deps."""
    return _create_test_app(repo)


@pytest.fixture
def client(app):
    """Synchronous test client using test lifespan."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _make_pipeline(repo, mock_openai_response) -> ExtractionPipeline:
    """Create a real ExtractionPipeline with a mocked archivist."""
    mock_client = AsyncMock()
    mock_client.responses.create.return_value = mock_openai_response

    archivist = ArchivistAgent.__new__(ArchivistAgent)
    archivist._client = mock_client
    archivist._model = "gpt-5-nano"
    archivist._vector_store = None
    archivist._embedding_engine = None
    archivist._system_prompt = "You are the archivist."

    settings = MagicMock(
        openai_api_key="test-key-e2e",
        auto_approve_threshold=0.85,
    )

    return ExtractionPipeline(
        repo=repo,
        vector_store=None,
        embedding_engine=None,
        settings=settings,
        archivist=archivist,
    )


def _create_capture(repo, content: str) -> str:
    """Store a capture in the DB and return its ID string."""
    import hashlib

    capture = Capture(
        raw_content=content,
        modality="text",
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
    )
    capture_id = repo.create_capture(capture)
    return str(capture_id)


# ═════════════════════════════════════════════════════════════════
# TEST SUITE
# ═════════════════════════════════════════════════════════════════


class TestCaptureToGraphE2E:
    """Full journey: user input → pipeline → nodes & edges visible on graph API."""

    async def test_capture_creates_nodes_and_edges(self, client, repo):
        """Golden path: text in → 3 nodes + 3 edges on the graph."""
        mock_resp = _make_openai_response(_coffee_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = (
            "Had coffee with Sam Chen today at Blue Bottle. "
            "He wants to see our pitch deck by Friday."
        )
        capture_id = _create_capture(repo, content)
        state = await pipeline.run(capture_id, content)

        assert state.status == "completed"
        assert state.error is None

        # Verify nodes via graph API
        nodes_resp = client.get("/api/v1/graph/nodes")
        assert nodes_resp.status_code == 200
        nodes = nodes_resp.json()
        assert len(nodes) == 3

        titles = {n["title"] for n in nodes}
        assert "Sam Chen" in titles
        assert "Coffee with Sam" in titles
        assert "Send pitch deck to Sam" in titles

        # Verify node types
        type_map = {n["title"]: n["node_type"] for n in nodes}
        assert type_map["Sam Chen"] == "PERSON"
        assert type_map["Coffee with Sam"] == "EVENT"
        assert type_map["Send pitch deck to Sam"] == "COMMITMENT"

        # Verify edges
        person_node = next(n for n in nodes if n["title"] == "Sam Chen")
        edges_resp = client.get(
            "/api/v1/graph/edges", params={"node_id": person_node["id"]}
        )
        assert edges_resp.status_code == 200
        edges = edges_resp.json()
        assert len(edges) >= 2

        edge_types = {e["edge_type"] for e in edges}
        assert "RELATED_TO" in edge_types
        assert "COMMITTED_TO" in edge_types

        # Verify stats
        stats = client.get("/api/v1/graph/stats").json()
        assert stats["node_count"] == 3
        assert stats["edge_count"] == 3

    async def test_single_node_no_edges(self, client, repo):
        """IDEA capture → single node, zero edges."""
        mock_resp = _make_openai_response(_idea_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "What if we built an AI-powered gardening assistant?"
        capture_id = _create_capture(repo, content)
        state = await pipeline.run(capture_id, content)

        assert state.status == "completed"

        nodes = client.get("/api/v1/graph/nodes").json()
        assert len(nodes) == 1
        assert nodes[0]["title"] == "AI-powered gardening assistant"
        assert nodes[0]["node_type"] == "IDEA"

        stats = client.get("/api/v1/graph/stats").json()
        assert stats["node_count"] == 1
        assert stats["edge_count"] == 0

    async def test_financial_node_creation(self, client, repo):
        """FINANCIAL_ITEM nodes are created with correct network."""
        mock_resp = _make_openai_response(_financial_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Paid $2,500.00 rent for 123 Main St apartment"
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        nodes = client.get("/api/v1/graph/nodes").json()
        assert len(nodes) == 1
        assert nodes[0]["node_type"] == "FINANCIAL_ITEM"
        assert nodes[0]["networks"] == ["FINANCIAL"]

    async def test_node_retrievable_by_id(self, client, repo):
        """Individual nodes are accessible via GET /graph/nodes/{id}."""
        mock_resp = _make_openai_response(_idea_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Idea: AI gardening assistant"
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        nodes = client.get("/api/v1/graph/nodes").json()
        node_id = nodes[0]["id"]

        detail = client.get(f"/api/v1/graph/nodes/{node_id}")
        assert detail.status_code == 200
        assert detail.json()["title"] == "AI-powered gardening assistant"
        assert detail.json()["id"] == node_id

    async def test_neighborhood_query(self, client, repo):
        """Neighborhood endpoint returns connected subgraph."""
        mock_resp = _make_openai_response(_coffee_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Coffee with Sam Chen, send pitch deck."
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        nodes = client.get("/api/v1/graph/nodes").json()
        person = next(n for n in nodes if n["node_type"] == "PERSON")

        neigh = client.get(
            f"/api/v1/graph/nodes/{person['id']}/neighborhood", params={"hops": 1}
        )
        assert neigh.status_code == 200
        subgraph = neigh.json()

        assert len(subgraph["nodes"]) == 3
        assert len(subgraph["edges"]) >= 2


class TestPipelineRouting:
    """Validation gate: AUTO, DIGEST, EXPLICIT routing."""

    async def test_high_confidence_auto_approved(self, client, repo):
        """Confidence >= 0.85 → AUTO route → nodes committed."""
        mock_resp = _make_openai_response(_coffee_proposal())  # confidence=0.90
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Coffee with Sam Chen at Blue Bottle"
        capture_id = _create_capture(repo, content)
        state = await pipeline.run(capture_id, content)

        assert state.route.value == "auto"
        assert state.status == "completed"

        nodes = client.get("/api/v1/graph/nodes").json()
        assert len(nodes) == 3

        # Proposal marked approved
        proposal = repo._conn.execute(
            "SELECT status, route FROM proposals WHERE capture_id = ?",
            [capture_id],
        ).fetchone()
        assert proposal[0] == "approved"
        assert proposal[1] == "auto"

    async def test_low_confidence_digest_route(self, client, repo):
        """Confidence < 0.85 → DIGEST route → nodes NOT committed."""
        mock_resp = _make_openai_response(_low_confidence_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Something about a meeting next week maybe"
        capture_id = _create_capture(repo, content)
        state = await pipeline.run(capture_id, content)

        assert state.route.value == "digest"

        # Nodes NOT committed (commit stage is a no-op for non-AUTO routes)
        nodes = client.get("/api/v1/graph/nodes").json()
        assert len(nodes) == 0

        proposal = repo._conn.execute(
            "SELECT status, route FROM proposals WHERE capture_id = ?",
            [capture_id],
        ).fetchone()
        assert proposal[0] == "pending"
        assert proposal[1] == "digest"


class TestClarificationProtocol:
    """Clarification flow (confidence=0.0, no nodes)."""

    async def test_clarification_no_nodes_created(self, client, repo):
        """Clarification response creates no nodes or proposals."""
        mock_resp = _make_openai_response(_clarification_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Update the project status"
        capture_id = _create_capture(repo, content)
        state = await pipeline.run(capture_id, content)

        assert state.clarification_needed is True

        nodes = client.get("/api/v1/graph/nodes").json()
        assert len(nodes) == 0

        stats = client.get("/api/v1/graph/stats").json()
        assert stats["node_count"] == 0
        assert stats["edge_count"] == 0


class TestDeduplication:
    """Content-hash based deduplication."""

    async def test_duplicate_capture_via_api_rejected(self, client, repo):
        """Submitting identical content twice returns 409 from API."""
        mock_resp = _make_openai_response(_idea_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "What if we built an AI-powered gardening assistant?"

        # Create capture and run pipeline manually (no background task)
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        # Second submission of same content via API → 409
        resp2 = client.post("/api/v1/captures", json={"content": content})
        assert resp2.status_code == 409

    async def test_different_content_accepted(self, client, repo):
        """Different content passes dedup check."""
        mock_resp = _make_openai_response(_idea_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        # First capture
        content1 = "First idea: gardening app"
        capture_id1 = _create_capture(repo, content1)
        await pipeline.run(capture_id1, content1)

        # Second capture with different content via API → accepted
        resp2 = client.post(
            "/api/v1/captures", json={"content": "Paid rent this month"}
        )
        assert resp2.status_code == 200


class TestPreprocessing:
    """Verify preprocessing transforms before LLM extraction."""

    async def test_currency_normalization(self, repo):
        """'50k' and 'bucks' are normalized before reaching the archivist."""
        captured_inputs = []

        mock_resp = _make_openai_response(_financial_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        original_extract = pipeline._archivist.extract

        async def capturing_extract(text, capture_id):
            captured_inputs.append(text)
            return await original_extract(text, capture_id)

        pipeline._archivist.extract = capturing_extract

        content = "Invested 50k in the startup and gave John 20 bucks"
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        assert len(captured_inputs) == 1
        processed = captured_inputs[0]
        assert "$50,000.00" in processed
        assert "$20.00" in processed

    async def test_date_normalization(self, repo):
        """Relative dates like 'tomorrow' are converted to ISO format."""
        import re

        captured_inputs = []

        mock_resp = _make_openai_response(_coffee_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        original_extract = pipeline._archivist.extract

        async def capturing_extract(text, capture_id):
            captured_inputs.append(text)
            return await original_extract(text, capture_id)

        pipeline._archivist.extract = capturing_extract

        content = "Meeting with Sam tomorrow at Blue Bottle"
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        assert len(captured_inputs) == 1
        processed = captured_inputs[0]
        assert "tomorrow" not in processed.lower()
        assert re.search(r"\d{4}-\d{2}-\d{2}", processed)


class TestMultipleCapturesAccumulate:
    """Multiple captures build up the graph incrementally."""

    async def test_two_captures_produce_combined_graph(self, client, repo):
        """Two independent captures result in all nodes on the graph."""
        # Capture 1: coffee meeting
        mock_resp1 = _make_openai_response(_coffee_proposal())
        pipeline1 = _make_pipeline(repo, mock_resp1)

        content1 = "Coffee with Sam Chen at Blue Bottle. Send pitch deck."
        capture_id1 = _create_capture(repo, content1)
        await pipeline1.run(capture_id1, content1)

        stats1 = client.get("/api/v1/graph/stats").json()
        assert stats1["node_count"] == 3
        assert stats1["edge_count"] == 3

        # Capture 2: new idea
        mock_resp2 = _make_openai_response(_idea_proposal())
        pipeline2 = _make_pipeline(repo, mock_resp2)

        content2 = "New idea: AI gardening assistant app"
        capture_id2 = _create_capture(repo, content2)
        await pipeline2.run(capture_id2, content2)

        stats2 = client.get("/api/v1/graph/stats").json()
        assert stats2["node_count"] == 4
        assert stats2["edge_count"] == 3

        nodes = client.get("/api/v1/graph/nodes").json()
        titles = {n["title"] for n in nodes}
        assert titles == {
            "Sam Chen",
            "Coffee with Sam",
            "Send pitch deck to Sam",
            "AI-powered gardening assistant",
        }


class TestNodeFilteringAfterCreation:
    """Graph query filters work on pipeline-created nodes."""

    async def test_filter_by_node_type(self, client, repo):
        """GET /graph/nodes?node_type=PERSON returns only people."""
        mock_resp = _make_openai_response(_coffee_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Coffee with Sam Chen, send pitch deck."
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        persons = client.get(
            "/api/v1/graph/nodes", params={"node_type": "PERSON"}
        ).json()
        assert len(persons) == 1
        assert persons[0]["title"] == "Sam Chen"

        events = client.get(
            "/api/v1/graph/nodes", params={"node_type": "EVENT"}
        ).json()
        assert len(events) == 1
        assert events[0]["title"] == "Coffee with Sam"

    async def test_filter_by_network(self, client, repo):
        """GET /graph/nodes?network=VENTURES returns nodes in that network."""
        mock_resp = _make_openai_response(_coffee_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Coffee with Sam Chen, send pitch deck."
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        ventures = client.get(
            "/api/v1/graph/nodes", params={"network": "VENTURES"}
        ).json()
        assert len(ventures) == 3


class TestCaptureRetrieval:
    """Captures can be retrieved after submission."""

    def test_get_capture_by_id(self, client, repo):
        """GET /captures/{id} returns the stored capture."""
        resp = client.post(
            "/api/v1/captures",
            json={"content": "Build an AI gardening app"},
        )
        capture_id = resp.json()["id"]

        detail = client.get(f"/api/v1/captures/{capture_id}")
        assert detail.status_code == 200
        data = detail.json()
        assert data["raw_content"] == "Build an AI gardening app"
        assert data["modality"] == "text"

    def test_get_nonexistent_capture(self, client):
        """GET /captures/{bad_id} returns 404."""
        resp = client.get(f"/api/v1/captures/{uuid4()}")
        assert resp.status_code == 404


class TestGraphNodeLifecycle:
    """Node CRUD operations on pipeline-created nodes."""

    async def test_update_node_after_creation(self, client, repo):
        """PATCH /graph/nodes/{id} updates a pipeline-created node."""
        mock_resp = _make_openai_response(_idea_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "AI gardening assistant idea"
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        nodes = client.get("/api/v1/graph/nodes").json()
        node_id = nodes[0]["id"]

        patch_resp = client.patch(
            f"/api/v1/graph/nodes/{node_id}",
            json={"title": "AI Garden Helper"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["title"] == "AI Garden Helper"

    async def test_delete_node_after_creation(self, client, repo):
        """DELETE /graph/nodes/{id} soft-deletes a pipeline-created node."""
        mock_resp = _make_openai_response(_idea_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "AI gardening assistant idea"
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        nodes = client.get("/api/v1/graph/nodes").json()
        node_id = nodes[0]["id"]

        del_resp = client.delete(f"/api/v1/graph/nodes/{node_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "deleted"

        nodes_after = client.get("/api/v1/graph/nodes").json()
        assert len(nodes_after) == 0

        stats = client.get("/api/v1/graph/stats").json()
        assert stats["node_count"] == 0


class TestEdgeIntegrity:
    """Verify edge source/target IDs reference real committed nodes."""

    async def test_edge_ids_resolve_to_committed_nodes(self, client, repo):
        """Every edge's source and target correspond to an existing node."""
        mock_resp = _make_openai_response(_coffee_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Coffee with Sam Chen, send pitch deck."
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        nodes = client.get("/api/v1/graph/nodes").json()
        node_ids = {n["id"] for n in nodes}

        all_edges = []
        for node in nodes:
            edges_resp = client.get(
                "/api/v1/graph/edges", params={"node_id": node["id"]}
            )
            all_edges.extend(edges_resp.json())

        # Deduplicate
        seen = set()
        for edge in all_edges:
            if edge["id"] in seen:
                continue
            seen.add(edge["id"])
            assert edge["source_id"] in node_ids, (
                f"Edge source {edge['source_id']} not in committed nodes"
            )
            assert edge["target_id"] in node_ids, (
                f"Edge target {edge['target_id']} not in committed nodes"
            )

    async def test_edge_categories_match_types(self, client, repo):
        """Edge category is consistent with edge type per ontology."""
        from memora.graph.ontology import EDGE_TYPE_CATEGORY

        mock_resp = _make_openai_response(_coffee_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Coffee with Sam Chen, send pitch deck."
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        nodes = client.get("/api/v1/graph/nodes").json()
        all_edges = []
        for node in nodes:
            edges_resp = client.get(
                "/api/v1/graph/edges", params={"node_id": node["id"]}
            )
            all_edges.extend(edges_resp.json())

        seen = set()
        for edge in all_edges:
            if edge["id"] in seen:
                continue
            seen.add(edge["id"])
            expected = EDGE_TYPE_CATEGORY.get(edge["edge_type"])
            if expected:
                assert edge["edge_category"] == expected, (
                    f"Edge {edge['edge_type']} should have category "
                    f"{expected}, got {edge['edge_category']}"
                )

    async def test_no_temp_ids_in_committed_edges(self, repo):
        """Temp IDs (e.g. 'person_1') are resolved to UUIDs after commit."""
        mock_resp = _make_openai_response(_coffee_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Coffee with Sam Chen, send pitch deck."
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        edges = repo._conn.execute("SELECT source_id, target_id FROM edges").fetchall()
        for source_id, target_id in edges:
            # Temp IDs are short strings like "person_1", UUIDs are 36 chars
            assert len(source_id) == 36, f"source_id looks like a temp ID: {source_id}"
            assert len(target_id) == 36, f"target_id looks like a temp ID: {target_id}"


class TestOpenAIIntegration:
    """Verify OpenAI mock is called correctly and responses are parsed."""

    async def test_openai_called_with_correct_input(self, repo):
        """Archivist sends the preprocessed text to OpenAI."""
        mock_resp = _make_openai_response(_idea_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Build an AI gardening assistant"
        capture_id = _create_capture(repo, content)
        await pipeline.run(capture_id, content)

        # The mock was called
        mock_client = pipeline._archivist._client
        mock_client.responses.create.assert_called_once()

        call_kwargs = mock_client.responses.create.call_args
        # Verify model
        assert call_kwargs.kwargs.get("model") == "gpt-5-nano"
        # Verify input contains the text
        input_text = call_kwargs.kwargs.get("input", "")
        assert "gardening assistant" in input_text.lower()
        # Verify JSON output format requested
        assert call_kwargs.kwargs.get("text") == {"format": {"type": "json_object"}}

    async def test_openai_api_error_fails_pipeline(self, repo):
        """OpenAI API error results in pipeline failure (no nodes created)."""
        import openai as openai_module

        mock_client = AsyncMock()
        mock_client.responses.create.side_effect = openai_module.APIError(
            message="Service unavailable",
            request=MagicMock(),
            body=None,
        )

        archivist = ArchivistAgent.__new__(ArchivistAgent)
        archivist._client = mock_client
        archivist._model = "gpt-5-nano"
        archivist._vector_store = None
        archivist._embedding_engine = None
        archivist._system_prompt = "You are the archivist."

        pipeline = ExtractionPipeline(
            repo=repo,
            settings=MagicMock(
                openai_api_key="test-key",
                auto_approve_threshold=0.85,
            ),
            archivist=archivist,
        )

        content = "Test content"
        capture_id = _create_capture(repo, content)
        state = await pipeline.run(capture_id, content)

        assert state.error is not None
        assert state.status == "failed"

        # No nodes created
        count = repo._conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE deleted = FALSE"
        ).fetchone()[0]
        assert count == 0

    async def test_malformed_json_from_openai(self, repo):
        """Malformed JSON from OpenAI results in pipeline failure."""
        bad_resp = MagicMock()
        bad_resp.output_text = "This is not valid JSON at all {broken"
        bad_resp.usage = MagicMock(input_tokens=100, output_tokens=50)

        # Both initial and retry return bad JSON
        mock_client = AsyncMock()
        mock_client.responses.create.return_value = bad_resp

        archivist = ArchivistAgent.__new__(ArchivistAgent)
        archivist._client = mock_client
        archivist._model = "gpt-5-nano"
        archivist._vector_store = None
        archivist._embedding_engine = None
        archivist._system_prompt = "You are the archivist."

        pipeline = ExtractionPipeline(
            repo=repo,
            settings=MagicMock(
                openai_api_key="test-key",
                auto_approve_threshold=0.85,
            ),
            archivist=archivist,
        )

        content = "Test content"
        capture_id = _create_capture(repo, content)
        state = await pipeline.run(capture_id, content)

        assert state.error is not None
        count = repo._conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE deleted = FALSE"
        ).fetchone()[0]
        assert count == 0


class TestProposalTracking:
    """Verify proposals are stored and trackable."""

    async def test_proposal_created_and_linked_to_capture(self, repo):
        """Pipeline creates a proposal linked to the source capture."""
        mock_resp = _make_openai_response(_coffee_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Coffee with Sam Chen"
        capture_id = _create_capture(repo, content)
        state = await pipeline.run(capture_id, content)

        assert state.proposal_id is not None

        proposal = repo._conn.execute(
            "SELECT capture_id, agent_id, confidence, human_summary FROM proposals WHERE id = ?",
            [state.proposal_id],
        ).fetchone()
        assert proposal[0] == capture_id
        assert proposal[1] == "archivist"
        assert proposal[2] == 0.90
        assert "Sam Chen" in proposal[3]

    async def test_proposal_data_contains_full_graph(self, repo):
        """Proposal data JSON contains all nodes and edges."""
        mock_resp = _make_openai_response(_coffee_proposal())
        pipeline = _make_pipeline(repo, mock_resp)

        content = "Coffee with Sam Chen, send pitch deck."
        capture_id = _create_capture(repo, content)
        state = await pipeline.run(capture_id, content)

        row = repo._conn.execute(
            "SELECT proposal_data FROM proposals WHERE id = ?",
            [state.proposal_id],
        ).fetchone()
        data = json.loads(row[0]) if isinstance(row[0], str) else row[0]

        assert len(data["nodes_to_create"]) == 3
        assert len(data["edges_to_create"]) == 3


class TestHealthEndpoint:
    """App health check."""

    def test_health_check(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
