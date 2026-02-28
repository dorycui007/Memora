"""Unit tests for SM-2 spaced repetition (Phase 5)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from memora.core.spaced_repetition import (
    DEFAULT_EASINESS_FACTOR,
    MIN_EASINESS_FACTOR,
    SpacedRepetition,
)
from memora.graph.repository import GraphRepository


def _insert_node(
    repo: GraphRepository,
    node_id: str | None = None,
    node_type: str = "CONCEPT",
    title: str = "Test Node",
    properties: dict | None = None,
    review_date: datetime | None = None,
) -> str:
    """Insert a raw node row for testing."""
    nid = node_id or str(uuid4())
    now = datetime.utcnow().isoformat()
    repo._conn.execute(
        """INSERT INTO nodes
           (id, node_type, title, content, content_hash, properties,
            confidence, networks, human_approved, access_count,
            decay_score, tags, created_at, updated_at, review_date, deleted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            nid,
            node_type,
            title,
            "",
            f"hash_{nid[:8]}",
            json.dumps(properties or {}),
            1.0,
            [],
            False,
            0,
            1.0,
            [],
            now,
            now,
            review_date.isoformat() if review_date else None,
            False,
        ],
    )
    return nid


class TestInitializeNode:
    def test_initialize_node(self, repo: GraphRepository):
        """Initializing a node should set SM-2 defaults in properties."""
        sr = SpacedRepetition(repo)
        nid = _insert_node(repo, title="Concept A")
        sr.initialize_node(nid)

        row = repo._conn.execute(
            "SELECT properties, review_date FROM nodes WHERE id = ?", [nid]
        ).fetchone()
        props = json.loads(row[0]) if isinstance(row[0], str) else row[0]

        assert props["easiness_factor"] == DEFAULT_EASINESS_FACTOR
        assert props["repetition_number"] == 0
        assert props["interval"] == 0
        assert "review_date" in props
        # Top-level review_date column should also be set
        assert row[1] is not None


class TestProcessReview:
    def test_process_review_quality_5(self, repo: GraphRepository):
        """Perfect review (quality=5) should increase interval."""
        sr = SpacedRepetition(repo)
        nid = _insert_node(repo, title="Concept B")
        sr.initialize_node(nid)

        # First review: interval should become 1, rep becomes 1
        result = sr.process_review(nid, quality=5)
        assert result["interval"] == 1
        assert result["repetition_number"] == 1

        # Second review: interval should become 6, rep becomes 2
        result = sr.process_review(nid, quality=5)
        assert result["interval"] == 6
        assert result["repetition_number"] == 2

        # Third review: interval = round(6 * EF), rep becomes 3
        result = sr.process_review(nid, quality=5)
        assert result["interval"] > 6
        assert result["repetition_number"] == 3

    def test_process_review_quality_0(self, repo: GraphRepository):
        """Failed review (quality=0) should reset interval to 1."""
        sr = SpacedRepetition(repo)
        nid = _insert_node(repo, title="Concept C")
        sr.initialize_node(nid)

        # Build up some repetitions first
        sr.process_review(nid, quality=5)
        sr.process_review(nid, quality=5)
        result = sr.process_review(nid, quality=5)
        assert result["repetition_number"] == 3

        # Now fail
        result = sr.process_review(nid, quality=0)
        assert result["interval"] == 1
        assert result["repetition_number"] == 0

    def test_easiness_factor_clamp(self, repo: GraphRepository):
        """EF should never drop below MIN_EASINESS_FACTOR (1.3)."""
        sr = SpacedRepetition(repo)
        nid = _insert_node(repo, title="Hard Concept")
        sr.initialize_node(nid)

        # Repeatedly give low (but passing) quality to drive EF down
        for _ in range(20):
            result = sr.process_review(nid, quality=3)

        assert result["easiness_factor"] >= MIN_EASINESS_FACTOR

    def test_interval_progression(self, repo: GraphRepository):
        """Verify SM-2 progression: first=1, second=6, then interval*EF."""
        sr = SpacedRepetition(repo)
        nid = _insert_node(repo, title="Progression Test")
        sr.initialize_node(nid)

        r1 = sr.process_review(nid, quality=4)
        assert r1["interval"] == 1

        r2 = sr.process_review(nid, quality=4)
        assert r2["interval"] == 6

        r3 = sr.process_review(nid, quality=4)
        expected = round(6 * r2["easiness_factor"])
        assert r3["interval"] == expected


class TestReviewQueue:
    def test_review_queue(self, repo: GraphRepository):
        """Nodes with review_date <= now should appear in the queue."""
        sr = SpacedRepetition(repo)

        # Node due yesterday -- should appear
        past = datetime.utcnow() - timedelta(days=1)
        nid_due = _insert_node(
            repo,
            title="Due Node",
            review_date=past,
            properties={"easiness_factor": 2.5, "review_date": past.isoformat()},
        )

        # Node due tomorrow -- should NOT appear
        future = datetime.utcnow() + timedelta(days=1)
        _insert_node(
            repo,
            title="Future Node",
            review_date=future,
            properties={"easiness_factor": 2.5, "review_date": future.isoformat()},
        )

        # Node with no review_date -- should NOT appear
        _insert_node(repo, title="No Review Node")

        queue = sr.get_review_queue()
        assert len(queue) == 1
        assert queue[0]["id"] == nid_due
        assert queue[0]["title"] == "Due Node"
