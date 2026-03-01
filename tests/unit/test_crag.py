"""Tests for CRAG (Corrective RAG) quality assessment."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from memora.agents.orchestrator import Orchestrator, QueryType


@dataclass
class FakeSearchResult:
    """Minimal search result for testing."""

    node_id: str = "abc"
    content: str = ""
    score: float = 0.8


class TestCRAGQualityAssessment:
    """Test the _assess_retrieval_quality method."""

    def _make_orchestrator(self, **settings_overrides):
        """Create an Orchestrator with mock settings."""
        settings = MagicMock()
        settings.crag_relevance_threshold = settings_overrides.get(
            "crag_relevance_threshold", 0.5
        )
        settings.crag_min_results = settings_overrides.get("crag_min_results", 3)
        settings.crag_term_coverage_threshold = settings_overrides.get(
            "crag_term_coverage_threshold", 0.3
        )
        return Orchestrator(
            api_key="",
            settings=settings,
        )

    def test_sufficient_quality(self):
        orch = self._make_orchestrator()
        results = [
            FakeSearchResult(score=0.9, content="machine learning algorithms"),
            FakeSearchResult(score=0.8, content="deep learning neural networks"),
            FakeSearchResult(score=0.7, content="training machine learning models"),
        ]
        quality = orch._assess_retrieval_quality("machine learning", results)
        assert quality == "sufficient"

    def test_poor_quality_insufficient_results(self):
        orch = self._make_orchestrator(crag_min_results=3)
        results = [
            FakeSearchResult(score=0.9, content="machine learning"),
        ]
        quality = orch._assess_retrieval_quality("machine learning", results)
        assert quality == "poor"

    def test_poor_quality_low_top_score(self):
        orch = self._make_orchestrator(crag_relevance_threshold=0.5)
        results = [
            FakeSearchResult(score=0.3, content="something unrelated"),
            FakeSearchResult(score=0.2, content="also unrelated"),
            FakeSearchResult(score=0.1, content="not relevant"),
        ]
        quality = orch._assess_retrieval_quality("machine learning", results)
        assert quality == "poor"

    def test_poor_quality_low_term_coverage(self):
        orch = self._make_orchestrator(crag_term_coverage_threshold=0.5)
        results = [
            FakeSearchResult(score=0.9, content="cooking recipes"),
            FakeSearchResult(score=0.8, content="baking tips"),
            FakeSearchResult(score=0.7, content="kitchen supplies"),
        ]
        quality = orch._assess_retrieval_quality(
            "quantum physics experiments", results
        )
        assert quality == "poor"

    def test_empty_results_is_poor(self):
        orch = self._make_orchestrator(crag_min_results=1)
        quality = orch._assess_retrieval_quality("test query", [])
        assert quality == "poor"

    def test_no_settings_uses_defaults(self):
        orch = Orchestrator(api_key="", settings=None)
        results = [
            FakeSearchResult(score=0.9, content="machine learning algorithms"),
            FakeSearchResult(score=0.8, content="deep learning neural networks"),
            FakeSearchResult(score=0.7, content="training machine learning models"),
        ]
        quality = orch._assess_retrieval_quality("machine learning", results)
        assert quality == "sufficient"


class TestCRAGRouting:
    """Test that CRAG affects routing decisions."""

    def test_analysis_with_poor_retrieval_escalates_to_council(self):
        orch = Orchestrator(api_key="")
        state = {
            "query_type": QueryType.ANALYSIS.value,
            "graph_context": {"retrieval_quality": "poor"},
        }
        route = orch._route_after_classify(state)
        assert route == "council_all"

    def test_analysis_with_sufficient_retrieval_stays_with_strategist(self):
        orch = Orchestrator(api_key="")
        state = {
            "query_type": QueryType.ANALYSIS.value,
            "graph_context": {"retrieval_quality": "sufficient"},
        }
        route = orch._route_after_classify(state)
        assert route == "strategist"

    def test_capture_not_affected_by_crag(self):
        orch = Orchestrator(api_key="")
        state = {
            "query_type": QueryType.CAPTURE.value,
            "graph_context": {"retrieval_quality": "poor"},
        }
        route = orch._route_after_classify(state)
        assert route == "archivist"

    def test_research_not_affected_by_crag(self):
        orch = Orchestrator(api_key="")
        state = {
            "query_type": QueryType.RESEARCH.value,
            "graph_context": {"retrieval_quality": "poor"},
        }
        route = orch._route_after_classify(state)
        assert route == "researcher"

    def test_missing_retrieval_quality_defaults_to_sufficient(self):
        orch = Orchestrator(api_key="")
        state = {
            "query_type": QueryType.ANALYSIS.value,
            "graph_context": {},
        }
        route = orch._route_after_classify(state)
        assert route == "strategist"
