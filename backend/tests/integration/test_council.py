"""Integration tests for the AI Council (Phase 4)."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from memora.graph.repository import GraphRepository
from memora.graph.models import (
    NetworkType,
    NodeType,
    PersonNode,
    EventNode,
)
from memora.agents.orchestrator import Orchestrator, QueryType, CouncilState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo():
    """In-memory DuckDB repository for testing."""
    r = GraphRepository(db_path=None)
    yield r
    r.close()


@pytest.fixture
def _patch_langgraph():
    """Patch LangGraph's StateGraph so the orchestrator can be constructed
    without actually compiling a real graph.  We only test helper methods
    directly, so compile() can return a stub."""
    with patch("memora.agents.orchestrator.StateGraph") as mock_sg:
        instance = MagicMock()
        instance.compile.return_value = MagicMock()
        mock_sg.return_value = instance
        yield mock_sg


@pytest.fixture
def orchestrator(_patch_langgraph, repo):
    """Orchestrator with mocked LLM clients and LangGraph."""
    with patch("memora.agents.orchestrator.ArchivistAgent"), \
         patch("memora.agents.orchestrator.StrategistAgent"), \
         patch("memora.agents.orchestrator.ResearcherAgent"):
        orch = Orchestrator(api_key="fake-key", repo=repo)
    return orch


# ---------------------------------------------------------------------------
# Query classification
# ---------------------------------------------------------------------------


class TestQueryClassification:
    """Verify the heuristic router in _classify_node."""

    def _make_state(self, query: str, query_type: str = "") -> CouncilState:
        return {
            "query_id": "test-id",
            "query": query,
            "query_type": query_type,
            "graph_context": {},
            "archivist_output": None,
            "strategist_output": None,
            "researcher_output": None,
            "synthesis": "",
            "confidence": 0.0,
            "citations": [],
            "deliberation_round": 0,
            "max_deliberation_rounds": 2,
            "high_disagreement": False,
            "error": None,
        }

    def test_capture_classification(self, orchestrator):
        """Queries about personal actions should classify as CAPTURE."""
        for query in [
            "I met Sam at Blue Bottle today",
            "I decided to pivot the startup",
            "Note to self: follow up on pitch deck",
            "I promised to send the report",
        ]:
            state = self._make_state(query)
            result = orchestrator._classify_node(state)
            assert result["query_type"] == QueryType.CAPTURE.value, (
                f"Expected capture for: {query!r}, got {result['query_type']}"
            )

    def test_analysis_classification(self, orchestrator):
        """Analytical questions should classify as ANALYSIS."""
        for query in [
            "Analyze my networking patterns",
            "Should I attend the conference?",
            "How am I doing on commitments?",
            "Give me a summary of my week",
        ]:
            state = self._make_state(query)
            result = orchestrator._classify_node(state)
            assert result["query_type"] == QueryType.ANALYSIS.value, (
                f"Expected analysis for: {query!r}, got {result['query_type']}"
            )

    def test_research_classification(self, orchestrator):
        """External lookup queries should classify as RESEARCH."""
        for query in [
            "What is the latest funding round for OpenAI?",
            "Look up Sam Altman's recent statements",
            "Research best practices for investor updates",
            "Explain how SAFE notes work",
        ]:
            state = self._make_state(query)
            result = orchestrator._classify_node(state)
            assert result["query_type"] == QueryType.RESEARCH.value, (
                f"Expected research for: {query!r}, got {result['query_type']}"
            )

    def test_council_classification(self, orchestrator):
        """Complex multi-faceted queries should classify as COUNCIL."""
        for query in [
            "Help me decide whether to take the job offer",
            "Comprehensive analysis of my networking ROI",
            "All things considered, is this partnership wise?",
        ]:
            state = self._make_state(query)
            result = orchestrator._classify_node(state)
            assert result["query_type"] == QueryType.COUNCIL.value, (
                f"Expected council for: {query!r}, got {result['query_type']}"
            )

    def test_explicit_override_respected(self, orchestrator):
        """When query_type is pre-set, classification should not overwrite it."""
        state = self._make_state("I met Sam today", query_type="research")
        result = orchestrator._classify_node(state)
        assert result["query_type"] == "research"

    def test_unknown_defaults_to_analysis(self, orchestrator):
        """Ambiguous queries should default to ANALYSIS."""
        state = self._make_state("The weather is nice today")
        result = orchestrator._classify_node(state)
        assert result["query_type"] == QueryType.ANALYSIS.value


# ---------------------------------------------------------------------------
# Council synthesis
# ---------------------------------------------------------------------------


class TestCouncilSynthesis:
    """Verify confidence-weighted merging in _synthesize_node."""

    def _base_state(self) -> CouncilState:
        return {
            "query_id": "synth-test",
            "query": "test",
            "query_type": QueryType.COUNCIL.value,
            "graph_context": {},
            "archivist_output": None,
            "strategist_output": None,
            "researcher_output": None,
            "synthesis": "",
            "confidence": 0.0,
            "citations": [],
            "deliberation_round": 0,
            "max_deliberation_rounds": 2,
            "high_disagreement": False,
            "error": None,
        }

    def test_single_agent_synthesis(self, orchestrator):
        """Synthesis with one agent output should pass through cleanly."""
        state = self._base_state()
        state["strategist_output"] = {
            "agent": "strategist",
            "content": "The network looks healthy.",
            "confidence": 0.85,
            "citations": ["node-abc"],
        }

        result = orchestrator._synthesize_node(state)
        assert "strategist" in result["synthesis"]
        assert result["confidence"] == pytest.approx(0.85)
        assert "node-abc" in result["citations"]
        assert result["high_disagreement"] is False

    def test_multi_agent_confidence_average(self, orchestrator):
        """Confidence should be the average of all contributing agents."""
        state = self._base_state()
        state["archivist_output"] = {
            "agent": "archivist",
            "content": "Extracted new nodes.",
            "confidence": 0.9,
            "citations": [],
        }
        state["strategist_output"] = {
            "agent": "strategist",
            "content": "Pattern detected.",
            "confidence": 0.7,
            "citations": ["ref-1"],
        }
        state["researcher_output"] = {
            "agent": "researcher",
            "content": "External data confirms.",
            "confidence": 0.8,
            "citations": ["ref-2"],
        }

        result = orchestrator._synthesize_node(state)
        expected_avg = (0.9 + 0.7 + 0.8) / 3.0
        assert result["confidence"] == pytest.approx(expected_avg)
        assert "archivist" in result["synthesis"]
        assert "strategist" in result["synthesis"]
        assert "researcher" in result["synthesis"]

    def test_error_outputs_excluded(self, orchestrator):
        """Agent outputs that contain errors should be excluded from synthesis."""
        state = self._base_state()
        state["archivist_output"] = {"error": "API timeout"}
        state["strategist_output"] = {
            "agent": "strategist",
            "content": "Analysis result.",
            "confidence": 0.75,
            "citations": [],
        }

        result = orchestrator._synthesize_node(state)
        assert result["confidence"] == pytest.approx(0.75)
        assert "archivist" not in result["synthesis"]

    def test_no_valid_outputs(self, orchestrator):
        """If no agent produced valid output, synthesis should note that."""
        state = self._base_state()
        state["archivist_output"] = {"error": "Failed"}

        result = orchestrator._synthesize_node(state)
        assert result["confidence"] == 0.0
        assert "No agent produced valid output" in result["synthesis"]

    def test_citations_deduplicated(self, orchestrator):
        """Citations from multiple agents should be deduplicated."""
        state = self._base_state()
        state["strategist_output"] = {
            "agent": "strategist",
            "content": "A",
            "confidence": 0.8,
            "citations": ["ref-1", "ref-2"],
        }
        state["researcher_output"] = {
            "agent": "researcher",
            "content": "B",
            "confidence": 0.7,
            "citations": ["ref-2", "ref-3"],
        }

        result = orchestrator._synthesize_node(state)
        assert sorted(result["citations"]) == ["ref-1", "ref-2", "ref-3"]

    def test_deliberation_round_incremented(self, orchestrator):
        """Each synthesis call should increment the deliberation round."""
        state = self._base_state()
        state["strategist_output"] = {
            "agent": "strategist",
            "content": "Round 1.",
            "confidence": 0.8,
            "citations": [],
        }
        result = orchestrator._synthesize_node(state)
        assert result["deliberation_round"] == 1


# ---------------------------------------------------------------------------
# Disagreement detection
# ---------------------------------------------------------------------------


class TestHighDisagreementDetection:
    """Verify that the synthesizer flags high disagreement."""

    def _base_state(self) -> CouncilState:
        return {
            "query_id": "disagree-test",
            "query": "test",
            "query_type": QueryType.COUNCIL.value,
            "graph_context": {},
            "archivist_output": None,
            "strategist_output": None,
            "researcher_output": None,
            "synthesis": "",
            "confidence": 0.0,
            "citations": [],
            "deliberation_round": 0,
            "max_deliberation_rounds": 2,
            "high_disagreement": False,
            "error": None,
        }

    def test_high_disagreement_flagged(self, orchestrator):
        """Confidence spread > 0.3 between agents should flag disagreement."""
        state = self._base_state()
        state["archivist_output"] = {
            "agent": "archivist",
            "content": "High confidence extraction.",
            "confidence": 0.95,
            "citations": [],
        }
        state["researcher_output"] = {
            "agent": "researcher",
            "content": "Low confidence research.",
            "confidence": 0.4,
            "citations": [],
        }

        result = orchestrator._synthesize_node(state)
        assert result["high_disagreement"] is True

    def test_low_disagreement_not_flagged(self, orchestrator):
        """Confidence spread <= 0.3 should NOT flag disagreement."""
        state = self._base_state()
        state["archivist_output"] = {
            "agent": "archivist",
            "content": "Good.",
            "confidence": 0.8,
            "citations": [],
        }
        state["strategist_output"] = {
            "agent": "strategist",
            "content": "Also good.",
            "confidence": 0.75,
            "citations": [],
        }

        result = orchestrator._synthesize_node(state)
        assert result["high_disagreement"] is False

    def test_single_agent_no_disagreement(self, orchestrator):
        """A single agent cannot disagree with itself."""
        state = self._base_state()
        state["strategist_output"] = {
            "agent": "strategist",
            "content": "Solo opinion.",
            "confidence": 0.5,
            "citations": [],
        }

        result = orchestrator._synthesize_node(state)
        assert result["high_disagreement"] is False

    def test_disagreement_boundary_exactly_03(self, orchestrator):
        """A spread of exactly 0.3 should NOT flag disagreement (> 0.3 required)."""
        state = self._base_state()
        state["archivist_output"] = {
            "agent": "archivist",
            "content": "A",
            "confidence": 0.9,
            "citations": [],
        }
        state["researcher_output"] = {
            "agent": "researcher",
            "content": "B",
            "confidence": 0.6,
            "citations": [],
        }

        result = orchestrator._synthesize_node(state)
        assert result["high_disagreement"] is False


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------


class TestRouting:
    """Verify _route_after_classify and _route_after_synthesize."""

    def _base_state(self, query_type: str = "analysis") -> CouncilState:
        return {
            "query_id": "route-test",
            "query": "test",
            "query_type": query_type,
            "graph_context": {},
            "archivist_output": None,
            "strategist_output": None,
            "researcher_output": None,
            "synthesis": "",
            "confidence": 0.0,
            "citations": [],
            "deliberation_round": 0,
            "max_deliberation_rounds": 2,
            "high_disagreement": False,
            "error": None,
        }

    def test_route_capture_to_archivist(self, orchestrator):
        state = self._base_state(QueryType.CAPTURE.value)
        assert orchestrator._route_after_classify(state) == "archivist"

    def test_route_research_to_researcher(self, orchestrator):
        state = self._base_state(QueryType.RESEARCH.value)
        assert orchestrator._route_after_classify(state) == "researcher"

    def test_route_analysis_to_strategist(self, orchestrator):
        state = self._base_state(QueryType.ANALYSIS.value)
        assert orchestrator._route_after_classify(state) == "strategist"

    def test_route_council_to_all_agents(self, orchestrator):
        """Council queries should route to all agents."""
        state = self._base_state(QueryType.COUNCIL.value)
        assert orchestrator._route_after_classify(state) == "council_all"

    def test_deliberation_continues_on_disagreement(self, orchestrator):
        """Council query with high disagreement and rounds left -> deliberate."""
        state = self._base_state(QueryType.COUNCIL.value)
        state["high_disagreement"] = True
        state["deliberation_round"] = 1
        state["max_deliberation_rounds"] = 3
        assert orchestrator._route_after_synthesize(state) == "deliberate"

    def test_deliberation_stops_at_max_rounds(self, orchestrator):
        """Even with disagreement, stop when max rounds reached."""
        state = self._base_state(QueryType.COUNCIL.value)
        state["high_disagreement"] = True
        state["deliberation_round"] = 2
        state["max_deliberation_rounds"] = 2
        assert orchestrator._route_after_synthesize(state) == "end"

    def test_no_deliberation_without_disagreement(self, orchestrator):
        """Council query without disagreement should end immediately."""
        state = self._base_state(QueryType.COUNCIL.value)
        state["high_disagreement"] = False
        state["deliberation_round"] = 0
        assert orchestrator._route_after_synthesize(state) == "end"

    def test_non_council_never_deliberates(self, orchestrator):
        """Non-council queries never deliberate, even with disagreement."""
        state = self._base_state(QueryType.ANALYSIS.value)
        state["high_disagreement"] = True
        state["deliberation_round"] = 0
        assert orchestrator._route_after_synthesize(state) == "end"
