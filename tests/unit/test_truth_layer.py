"""Tests for the Truth Layer — verified fact storage and contradiction detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

import duckdb
import numpy as np

from memora.core.truth_layer import (
    DUPLICATE_SIMILARITY_THRESHOLD,
    SOURCE_CONFIDENCE_WEIGHTS,
    FactLifecycle,
    FactStatus,
    TruthLayer,
)


@pytest.fixture
def conn():
    """In-memory DuckDB connection for truth layer tests."""
    c = duckdb.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def truth_layer(conn):
    tl = TruthLayer(conn)
    # Prevent lazy-loading of the NLI model in basic tests so keyword-based
    # tests exercise the keyword path without interference.
    tl._nli_load_failed = True
    return tl


def _deposit_uncalibrated(tl, **kwargs):
    """Helper: deposit a fact bypassing confidence calibration."""
    kwargs.setdefault("calibrate", False)
    return tl.deposit_fact(**kwargs)


class TestFactDeposit:
    def test_deposit_returns_id(self, truth_layer):
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=str(uuid4()),
            statement="Earth orbits the Sun",
            confidence=0.99,
        )
        assert fid is not None
        assert len(fid) == 36  # UUID format

    def test_deposit_dynamic_sets_next_check(self, truth_layer):
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=str(uuid4()),
            statement="Current salary is 100k",
            confidence=0.9,
            lifecycle=FactLifecycle.DYNAMIC,
            recheck_interval_days=30,
        )
        fact = truth_layer.get_fact(fid)
        assert fact is not None
        assert fact["next_check"] is not None
        assert fact["lifecycle"] == "dynamic"

    def test_deposit_static_no_next_check(self, truth_layer):
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=str(uuid4()),
            statement="Born in New York",
            confidence=0.99,
            lifecycle=FactLifecycle.STATIC,
        )
        fact = truth_layer.get_fact(fid)
        assert fact["next_check"] is None
        assert fact["lifecycle"] == "static"

    def test_deposit_with_metadata(self, truth_layer):
        meta = {"source": "tax_return", "year": 2025}
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=str(uuid4()),
            statement="Annual income is 150k",
            confidence=0.95,
            metadata=meta,
        )
        fact = truth_layer.get_fact(fid)
        assert fact["metadata"]["source"] == "tax_return"
        assert fact["metadata"]["year"] == 2025

    def test_deposit_sets_active_status(self, truth_layer):
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=str(uuid4()),
            statement="Test fact",
            confidence=0.8,
        )
        fact = truth_layer.get_fact(fid)
        assert fact["status"] == "active"


class TestFactRetrieval:
    def test_get_nonexistent_returns_none(self, truth_layer):
        result = truth_layer.get_fact(str(uuid4()))
        assert result is None

    def test_query_by_node_id(self, truth_layer):
        node_id = str(uuid4())
        _deposit_uncalibrated(truth_layer, node_id=node_id, statement="Fact A", confidence=0.8)
        _deposit_uncalibrated(truth_layer, node_id=node_id, statement="Fact B", confidence=0.9)
        _deposit_uncalibrated(truth_layer, node_id=str(uuid4()), statement="Fact C", confidence=0.7)

        results = truth_layer.query_facts(node_id=node_id)
        assert len(results) == 2

    def test_query_by_status(self, truth_layer):
        nid = str(uuid4())
        _deposit_uncalibrated(truth_layer, node_id=nid, statement="Active fact", confidence=0.9)
        fid2 = _deposit_uncalibrated(truth_layer, node_id=nid, statement="To retire", confidence=0.5)
        truth_layer.retire_fact(fid2)

        active = truth_layer.query_facts(status="active")
        assert len(active) == 1
        assert active[0]["statement"] == "Active fact"

    def test_query_by_lifecycle(self, truth_layer):
        nid = str(uuid4())
        _deposit_uncalibrated(
            truth_layer, node_id=nid, statement="Static", confidence=0.9,
            lifecycle=FactLifecycle.STATIC,
        )
        _deposit_uncalibrated(
            truth_layer, node_id=nid, statement="Dynamic", confidence=0.8,
            lifecycle=FactLifecycle.DYNAMIC,
        )

        static = truth_layer.query_facts(lifecycle="static")
        assert len(static) == 1
        assert static[0]["statement"] == "Static"

    def test_query_pagination(self, truth_layer):
        nid = str(uuid4())
        for i in range(5):
            _deposit_uncalibrated(truth_layer, node_id=nid, statement=f"Fact {i}", confidence=0.8)

        page1 = truth_layer.query_facts(limit=2, offset=0)
        assert len(page1) == 2
        page2 = truth_layer.query_facts(limit=2, offset=2)
        assert len(page2) == 2


class TestContradictionDetection:
    def test_no_contradictions_for_new_node(self, truth_layer):
        result = truth_layer.check_contradiction(
            statement="Alice works at Google",
            node_id=str(uuid4()),
        )
        assert result == []

    def test_detects_potential_contradiction(self, truth_layer):
        node_id = str(uuid4())
        _deposit_uncalibrated(
            truth_layer,
            node_id=node_id,
            statement="Alice works at Google as a senior engineer",
            confidence=0.9,
        )
        # Different statement with overlapping keywords
        contradictions = truth_layer.check_contradiction(
            statement="Alice works at Microsoft as a senior engineer",
            node_id=node_id,
        )
        assert len(contradictions) >= 1

    def test_no_contradiction_for_different_topic(self, truth_layer):
        node_id = str(uuid4())
        _deposit_uncalibrated(
            truth_layer,
            node_id=node_id,
            statement="Alice works at Google",
            confidence=0.9,
        )
        contradictions = truth_layer.check_contradiction(
            statement="Bob likes hiking on weekends",
            node_id=node_id,
        )
        assert len(contradictions) == 0

    def test_identical_statement_not_contradiction(self, truth_layer):
        node_id = str(uuid4())
        _deposit_uncalibrated(
            truth_layer,
            node_id=node_id,
            statement="Alice works at Google",
            confidence=0.9,
        )
        contradictions = truth_layer.check_contradiction(
            statement="Alice works at Google",
            node_id=node_id,
        )
        assert len(contradictions) == 0


class TestCrossNodeContradiction:
    """P0: Cross-node contradiction detection."""

    def test_cross_node_finds_contradiction_across_entities(self, truth_layer):
        node_a = str(uuid4())
        node_b = str(uuid4())
        _deposit_uncalibrated(
            truth_layer,
            node_id=node_a,
            statement="Alice works at Google as a senior engineer",
            confidence=0.9,
        )
        # Same person, different node, contradicting employer
        contradictions = truth_layer.check_contradiction(
            statement="Alice works at Microsoft as a senior engineer",
            node_id=node_b,
            cross_node=True,
        )
        assert len(contradictions) >= 1

    def test_same_node_only_misses_cross_node_contradiction(self, truth_layer):
        node_a = str(uuid4())
        node_b = str(uuid4())
        _deposit_uncalibrated(
            truth_layer,
            node_id=node_a,
            statement="Alice works at Google as a senior engineer",
            confidence=0.9,
        )
        # Without cross_node, node_b has no facts, so no contradiction
        contradictions = truth_layer.check_contradiction(
            statement="Alice works at Microsoft as a senior engineer",
            node_id=node_b,
            cross_node=False,
        )
        assert len(contradictions) == 0

    def test_cross_node_skips_identical(self, truth_layer):
        node_a = str(uuid4())
        node_b = str(uuid4())
        _deposit_uncalibrated(
            truth_layer,
            node_id=node_a,
            statement="Alice works at Google",
            confidence=0.9,
        )
        contradictions = truth_layer.check_contradiction(
            statement="Alice works at Google",
            node_id=node_b,
            cross_node=True,
        )
        assert len(contradictions) == 0


class TestNLIContradiction:
    """P1: NLI-based contradiction detection (mocked)."""

    def test_nli_detects_contradiction(self, conn):
        mock_nli = MagicMock()
        # Simulate NLI output: [contradiction, entailment, neutral]
        mock_nli.predict.return_value = [
            np.array([0.85, 0.05, 0.10]),  # contradiction
        ]

        tl = TruthLayer(conn, nli_model=mock_nli)
        node_id = str(uuid4())
        _deposit_uncalibrated(
            tl, node_id=node_id,
            statement="Alice earns $100k",
            confidence=0.9,
        )

        contradictions = tl.check_contradiction(
            statement="Alice earns $150k",
            node_id=node_id,
        )
        assert len(contradictions) == 1
        assert contradictions[0]["_contradiction_score"] > 0.5

    def test_nli_no_contradiction_for_neutral(self, conn):
        mock_nli = MagicMock()
        mock_nli.predict.return_value = [
            np.array([0.05, 0.10, 0.85]),  # neutral
        ]

        tl = TruthLayer(conn, nli_model=mock_nli)
        node_id = str(uuid4())
        _deposit_uncalibrated(
            tl, node_id=node_id,
            statement="Alice works at Google",
            confidence=0.9,
        )

        contradictions = tl.check_contradiction(
            statement="Alice got promoted to VP",
            node_id=node_id,
        )
        assert len(contradictions) == 0

    def test_nli_entailment_not_flagged(self, conn):
        mock_nli = MagicMock()
        mock_nli.predict.return_value = [
            np.array([0.05, 0.85, 0.10]),  # entailment
        ]

        tl = TruthLayer(conn, nli_model=mock_nli)
        node_id = str(uuid4())
        _deposit_uncalibrated(
            tl, node_id=node_id,
            statement="Alice got promoted",
            confidence=0.9,
        )

        contradictions = tl.check_contradiction(
            statement="Alice got promoted to VP",
            node_id=node_id,
        )
        assert len(contradictions) == 0

    def test_nli_fallback_on_failure(self, conn):
        mock_nli = MagicMock()
        mock_nli.predict.side_effect = RuntimeError("model failed")

        tl = TruthLayer(conn, nli_model=mock_nli)
        node_id = str(uuid4())
        _deposit_uncalibrated(
            tl, node_id=node_id,
            statement="Alice works at Google as a senior engineer",
            confidence=0.9,
        )

        # Should fall back to keyword-based detection without raising
        contradictions = tl.check_contradiction(
            statement="Alice works at Microsoft as a senior engineer",
            node_id=node_id,
        )
        # Keyword fallback should still catch this
        assert len(contradictions) >= 1

    def test_nli_lazy_load_failure_sets_flag(self, conn):
        tl = TruthLayer(conn)
        assert tl._nli_model is None
        assert tl._nli_load_failed is False

        with patch("memora.core.truth_layer.TruthLayer._get_nli_model", return_value=None):
            # _check_contradiction_nli returns None when no model
            result = tl._check_contradiction_nli("test", [{"statement": "other"}])
            assert result is None


class TestStaleFacts:
    def test_get_stale_dynamic_facts(self, truth_layer, conn):
        node_id = str(uuid4())
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=node_id,
            statement="Current rent is $2000/month",
            confidence=0.9,
            lifecycle=FactLifecycle.DYNAMIC,
            recheck_interval_days=1,
        )
        # Force next_check to the past
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        conn.execute(
            "UPDATE verified_facts SET next_check = ? WHERE id = ?",
            [past, fid],
        )

        stale = truth_layer.get_stale_facts()
        assert len(stale) >= 1
        assert stale[0]["id"] == fid

    def test_active_facts_not_stale(self, truth_layer):
        _deposit_uncalibrated(
            truth_layer,
            node_id=str(uuid4()),
            statement="Future check",
            confidence=0.9,
            lifecycle=FactLifecycle.DYNAMIC,
            recheck_interval_days=365,
        )
        stale = truth_layer.get_stale_facts()
        assert len(stale) == 0


class TestFactChecks:
    def test_record_check_confirmed(self, truth_layer):
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=str(uuid4()),
            statement="Test fact for checking",
            confidence=0.8,
            lifecycle=FactLifecycle.DYNAMIC,
        )
        check_id = truth_layer.record_check(
            fact_id=fid,
            check_type="manual_review",
            result="confirmed",
            evidence="Verified via document",
            checked_by="user",
        )
        assert check_id is not None

        # Fact should remain active
        fact = truth_layer.get_fact(fid)
        assert fact["status"] == "active"

        # Check record should exist
        checks = truth_layer.get_checks_for_fact(fid)
        assert len(checks) == 1
        assert checks[0]["result"] == "confirmed"

    def test_record_check_contradicted(self, truth_layer):
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=str(uuid4()),
            statement="Salary is 100k",
            confidence=0.8,
        )
        truth_layer.record_check(
            fact_id=fid,
            check_type="contradiction",
            result="contradicted",
            evidence="New data shows salary is 120k",
        )
        fact = truth_layer.get_fact(fid)
        assert fact["status"] == "contradicted"

    def test_confirmed_resets_next_check(self, truth_layer):
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=str(uuid4()),
            statement="Dynamic fact",
            confidence=0.8,
            lifecycle=FactLifecycle.DYNAMIC,
            recheck_interval_days=30,
        )
        original = truth_layer.get_fact(fid)
        original_next = original["next_check"]

        truth_layer.record_check(
            fact_id=fid, check_type="review", result="confirmed",
        )
        updated = truth_layer.get_fact(fid)
        # next_check should be updated (pushed forward)
        assert updated["next_check"] != original_next


class TestFactRetirement:
    def test_retire_fact(self, truth_layer):
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=str(uuid4()),
            statement="Old address: 123 Main St",
            confidence=0.9,
        )
        truth_layer.retire_fact(fid, reason="Moved to new address")

        fact = truth_layer.get_fact(fid)
        assert fact["status"] == "retired"

    def test_retire_creates_check_record(self, truth_layer):
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=str(uuid4()),
            statement="Retired fact",
            confidence=0.9,
        )
        truth_layer.retire_fact(fid, reason="No longer relevant")

        checks = truth_layer.get_checks_for_fact(fid)
        assert len(checks) == 1
        assert checks[0]["check_type"] == "retirement"
        assert checks[0]["result"] == "retired"


class TestConfidenceCalibration:
    """P5: Source-specific confidence normalization."""

    def test_pipeline_auto_discounted(self):
        raw = 0.9
        calibrated = TruthLayer.calibrate_confidence(raw, "pipeline_auto")
        expected = raw * SOURCE_CONFIDENCE_WEIGHTS["pipeline_auto"]
        assert calibrated == round(expected, 4)
        assert calibrated < raw

    def test_user_source_unchanged(self):
        raw = 0.85
        calibrated = TruthLayer.calibrate_confidence(raw, "user")
        assert calibrated == raw

    def test_unknown_source_gets_default_discount(self):
        raw = 0.9
        calibrated = TruthLayer.calibrate_confidence(raw, "unknown_source")
        # Default weight is 0.80
        assert calibrated == round(raw * 0.80, 4)

    def test_calibration_clamps_to_bounds(self):
        assert TruthLayer.calibrate_confidence(1.5, "user") == 1.0
        assert TruthLayer.calibrate_confidence(-0.1, "user") == 0.0

    def test_deposit_applies_calibration_by_default(self, truth_layer):
        fid = truth_layer.deposit_fact(
            node_id=str(uuid4()),
            statement="Calibrated fact",
            confidence=1.0,
            verified_by="pipeline_auto",
        )
        fact = truth_layer.get_fact(fid)
        assert fact["confidence"] == SOURCE_CONFIDENCE_WEIGHTS["pipeline_auto"]

    def test_deposit_skips_calibration_when_disabled(self, truth_layer):
        fid = truth_layer.deposit_fact(
            node_id=str(uuid4()),
            statement="Uncalibrated fact",
            confidence=1.0,
            verified_by="pipeline_auto",
            calibrate=False,
        )
        fact = truth_layer.get_fact(fid)
        assert fact["confidence"] == 1.0


class TestDuplicateDetection:
    """P4: Duplicate fact detection on deposit."""

    def test_exact_duplicate_returns_none(self, truth_layer):
        node_id = str(uuid4())
        fid1 = _deposit_uncalibrated(
            truth_layer,
            node_id=node_id,
            statement="Alice works at Google",
            confidence=0.9,
        )
        assert fid1 is not None

        fid2 = _deposit_uncalibrated(
            truth_layer,
            node_id=node_id,
            statement="Alice works at Google",
            confidence=0.9,
        )
        assert fid2 is None  # duplicate detected

    def test_case_insensitive_duplicate(self, truth_layer):
        node_id = str(uuid4())
        _deposit_uncalibrated(
            truth_layer, node_id=node_id,
            statement="Alice works at Google",
            confidence=0.9,
        )
        fid2 = _deposit_uncalibrated(
            truth_layer, node_id=node_id,
            statement="alice works at google",
            confidence=0.9,
        )
        assert fid2 is None

    def test_different_node_allows_same_statement(self, truth_layer):
        _deposit_uncalibrated(
            truth_layer, node_id=str(uuid4()),
            statement="Alice works at Google",
            confidence=0.9,
        )
        fid2 = _deposit_uncalibrated(
            truth_layer, node_id=str(uuid4()),
            statement="Alice works at Google",
            confidence=0.9,
        )
        assert fid2 is not None

    def test_different_statement_allowed(self, truth_layer):
        node_id = str(uuid4())
        _deposit_uncalibrated(
            truth_layer, node_id=node_id,
            statement="Alice works at Google",
            confidence=0.9,
        )
        fid2 = _deposit_uncalibrated(
            truth_layer, node_id=node_id,
            statement="Bob works at Microsoft",
            confidence=0.9,
        )
        assert fid2 is not None

    def test_semantic_duplicate_with_embedding_engine(self, conn):
        mock_engine = MagicMock()
        # Return nearly identical embeddings for duplicate statements
        base_vec = [0.1] * 768
        mock_engine.embed_text.return_value = {"dense": base_vec, "sparse": {}}

        tl = TruthLayer(conn, embedding_engine=mock_engine)
        node_id = str(uuid4())

        # First deposit: embed_text called but no duplicate found (no existing facts)
        fid1 = _deposit_uncalibrated(
            tl, node_id=node_id,
            statement="Alice is employed at Google",
            confidence=0.9,
        )
        assert fid1 is not None

        # Second deposit: identical embeddings => cosine similarity = 1.0 > threshold
        fid2 = _deposit_uncalibrated(
            tl, node_id=node_id,
            statement="Alice works at Google Inc",
            confidence=0.9,
        )
        assert fid2 is None


class TestConfidenceDecay:
    """P3: Automatic confidence decay for overdue dynamic facts."""

    def test_decay_reduces_confidence(self, truth_layer, conn):
        node_id = str(uuid4())
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=node_id,
            statement="Rent is $2000",
            confidence=0.9,
            lifecycle=FactLifecycle.DYNAMIC,
            recheck_interval_days=30,
        )
        # Force next_check to the past
        past = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        conn.execute("UPDATE verified_facts SET next_check = ? WHERE id = ?", [past, fid])

        updated = truth_layer.decay_stale_confidence(decay_rate=0.10)
        assert updated == 1

        fact = truth_layer.get_fact(fid)
        assert fact["confidence"] < 0.9

    def test_decay_marks_stale_below_threshold(self, truth_layer, conn):
        node_id = str(uuid4())
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=node_id,
            statement="Rent is $2000",
            confidence=0.3,  # Already low
            lifecycle=FactLifecycle.DYNAMIC,
            recheck_interval_days=30,
        )
        past = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        conn.execute("UPDATE verified_facts SET next_check = ? WHERE id = ?", [past, fid])

        truth_layer.decay_stale_confidence(decay_rate=0.10, stale_threshold=0.4)

        fact = truth_layer.get_fact(fid)
        assert fact["status"] == FactStatus.STALE.value
        assert fact["confidence"] < 0.3

    def test_decay_records_check(self, truth_layer, conn):
        node_id = str(uuid4())
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=node_id,
            statement="Test decay audit",
            confidence=0.8,
            lifecycle=FactLifecycle.DYNAMIC,
            recheck_interval_days=30,
        )
        past = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        conn.execute("UPDATE verified_facts SET next_check = ? WHERE id = ?", [past, fid])

        truth_layer.decay_stale_confidence()

        checks = truth_layer.get_checks_for_fact(fid)
        decay_checks = [c for c in checks if c["check_type"] == "confidence_decay"]
        assert len(decay_checks) == 1
        assert "Confidence" in decay_checks[0]["evidence"]

    def test_no_decay_when_no_stale_facts(self, truth_layer):
        _deposit_uncalibrated(
            truth_layer,
            node_id=str(uuid4()),
            statement="Future fact",
            confidence=0.9,
            lifecycle=FactLifecycle.DYNAMIC,
            recheck_interval_days=365,
        )
        updated = truth_layer.decay_stale_confidence()
        assert updated == 0

    def test_decay_multiple_missed_intervals(self, truth_layer, conn):
        node_id = str(uuid4())
        fid = _deposit_uncalibrated(
            truth_layer,
            node_id=node_id,
            statement="Old fact",
            confidence=0.9,
            lifecycle=FactLifecycle.DYNAMIC,
            recheck_interval_days=30,
        )
        # 91 days overdue = 4 missed intervals (91/30 + 1)
        past = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
        conn.execute("UPDATE verified_facts SET next_check = ? WHERE id = ?", [past, fid])

        truth_layer.decay_stale_confidence(decay_rate=0.10)

        fact = truth_layer.get_fact(fid)
        # 0.9 * (0.9^4) = 0.9 * 0.6561 ≈ 0.5905
        assert fact["confidence"] < 0.6
        assert fact["confidence"] > 0.5


class TestBriefingStaleFacts:
    """P2: Stale fact surfacing without confidence filter."""

    def test_stale_facts_surfaced_regardless_of_confidence(self, conn):
        from memora.core.briefing import BriefingCollector

        tl = TruthLayer(conn)
        node_id = str(uuid4())

        # Deposit a high-confidence fact that becomes stale
        fid = _deposit_uncalibrated(
            tl,
            node_id=node_id,
            statement="Salary is $120k",
            confidence=0.95,
            lifecycle=FactLifecycle.DYNAMIC,
            recheck_interval_days=1,
        )
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        conn.execute("UPDATE verified_facts SET next_check = ? WHERE id = ?", [past, fid])

        # Use a mock repo since we only need the truth_layer part
        mock_repo = MagicMock()
        mock_repo.get_latest_health_scores.return_value = []
        mock_repo.get_nodes_by_date_range.return_value = []
        mock_repo.get_actions_by_date_range.return_value = []
        mock_repo.get_recent_bridges.return_value = []
        mock_repo.get_patterns.return_value = []

        collector = BriefingCollector(mock_repo, truth_layer=tl)
        data = collector.collect()

        # The stale fact should appear even though confidence is 0.95
        assert len(data["urgent"]["stale_facts"]) == 1
        assert data["urgent"]["stale_facts"][0]["id"] == fid
