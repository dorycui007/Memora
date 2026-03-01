"""Tests for the Truth Layer — verified fact storage and contradiction detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

import duckdb

from memora.core.truth_layer import TruthLayer, FactStatus, FactLifecycle


@pytest.fixture
def conn():
    """In-memory DuckDB connection for truth layer tests."""
    c = duckdb.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def truth_layer(conn):
    return TruthLayer(conn)


class TestFactDeposit:
    def test_deposit_returns_id(self, truth_layer):
        fid = truth_layer.deposit_fact(
            node_id=str(uuid4()),
            statement="Earth orbits the Sun",
            confidence=0.99,
        )
        assert fid is not None
        assert len(fid) == 36  # UUID format

    def test_deposit_dynamic_sets_next_check(self, truth_layer):
        fid = truth_layer.deposit_fact(
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
        fid = truth_layer.deposit_fact(
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
        fid = truth_layer.deposit_fact(
            node_id=str(uuid4()),
            statement="Annual income is 150k",
            confidence=0.95,
            metadata=meta,
        )
        fact = truth_layer.get_fact(fid)
        assert fact["metadata"]["source"] == "tax_return"
        assert fact["metadata"]["year"] == 2025

    def test_deposit_sets_active_status(self, truth_layer):
        fid = truth_layer.deposit_fact(
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
        truth_layer.deposit_fact(node_id=node_id, statement="Fact A", confidence=0.8)
        truth_layer.deposit_fact(node_id=node_id, statement="Fact B", confidence=0.9)
        truth_layer.deposit_fact(node_id=str(uuid4()), statement="Fact C", confidence=0.7)

        results = truth_layer.query_facts(node_id=node_id)
        assert len(results) == 2

    def test_query_by_status(self, truth_layer):
        nid = str(uuid4())
        fid1 = truth_layer.deposit_fact(node_id=nid, statement="Active fact", confidence=0.9)
        fid2 = truth_layer.deposit_fact(node_id=nid, statement="To retire", confidence=0.5)
        truth_layer.retire_fact(fid2)

        active = truth_layer.query_facts(status="active")
        assert len(active) == 1
        assert active[0]["statement"] == "Active fact"

    def test_query_by_lifecycle(self, truth_layer):
        nid = str(uuid4())
        truth_layer.deposit_fact(
            node_id=nid, statement="Static", confidence=0.9,
            lifecycle=FactLifecycle.STATIC,
        )
        truth_layer.deposit_fact(
            node_id=nid, statement="Dynamic", confidence=0.8,
            lifecycle=FactLifecycle.DYNAMIC,
        )

        static = truth_layer.query_facts(lifecycle="static")
        assert len(static) == 1
        assert static[0]["statement"] == "Static"

    def test_query_pagination(self, truth_layer):
        nid = str(uuid4())
        for i in range(5):
            truth_layer.deposit_fact(node_id=nid, statement=f"Fact {i}", confidence=0.8)

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
        truth_layer.deposit_fact(
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
        truth_layer.deposit_fact(
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
        truth_layer.deposit_fact(
            node_id=node_id,
            statement="Alice works at Google",
            confidence=0.9,
        )
        contradictions = truth_layer.check_contradiction(
            statement="Alice works at Google",
            node_id=node_id,
        )
        assert len(contradictions) == 0


class TestStaleFacts:
    def test_get_stale_dynamic_facts(self, truth_layer, conn):
        node_id = str(uuid4())
        fid = truth_layer.deposit_fact(
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
        truth_layer.deposit_fact(
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
        fid = truth_layer.deposit_fact(
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
        fid = truth_layer.deposit_fact(
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
        fid = truth_layer.deposit_fact(
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
        fid = truth_layer.deposit_fact(
            node_id=str(uuid4()),
            statement="Old address: 123 Main St",
            confidence=0.9,
        )
        truth_layer.retire_fact(fid, reason="Moved to new address")

        fact = truth_layer.get_fact(fid)
        assert fact["status"] == "retired"

    def test_retire_creates_check_record(self, truth_layer):
        fid = truth_layer.deposit_fact(
            node_id=str(uuid4()),
            statement="Retired fact",
            confidence=0.9,
        )
        truth_layer.retire_fact(fid, reason="No longer relevant")

        checks = truth_layer.get_checks_for_fact(fid)
        assert len(checks) == 1
        assert checks[0]["check_type"] == "retirement"
        assert checks[0]["result"] == "retired"
