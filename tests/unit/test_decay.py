"""Unit tests for decay scoring (Phase 5)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from math import exp, log
from uuid import uuid4

import pytest

from memora.core.decay import DecayScoring
from memora.graph.repository import GraphRepository


def _insert_node(
    repo: GraphRepository,
    node_id: str | None = None,
    node_type: str = "NOTE",
    title: str = "Test Node",
    content: str = "",
    networks: list[str] | None = None,
    last_accessed: datetime | None = None,
    decay_score: float = 1.0,
    deleted: bool = False,
    properties: dict | None = None,
    access_count: int = 0,
    created_at: datetime | None = None,
) -> str:
    """Helper to insert a raw node row directly into DuckDB."""
    nid = node_id or str(uuid4())
    now_str = (created_at or datetime.now(timezone.utc)).isoformat()
    content_hash = f"hash_{nid[:8]}"
    repo._conn.execute(
        """INSERT INTO nodes
           (id, node_type, title, content, content_hash, properties,
            confidence, networks, human_approved, access_count,
            decay_score, tags, created_at, updated_at, last_accessed, deleted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            nid,
            node_type,
            title,
            content,
            content_hash,
            json.dumps(properties or {}),
            1.0,
            networks or [],
            False,
            access_count,
            decay_score,
            [],
            now_str,
            now_str,
            last_accessed.isoformat() if last_accessed else None,
            deleted,
        ],
    )
    return nid


class TestComputeDecay:
    def test_compute_decay_fresh_node(self, repo: GraphRepository):
        """Decay should be ~1.0 for a node accessed just now."""
        scorer = DecayScoring(repo)
        now = datetime.now(timezone.utc)
        score = scorer.compute_decay(now, lambda_val=0.05)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_compute_decay_old_node(self, repo: GraphRepository):
        """Decay should decrease significantly for a node accessed long ago."""
        scorer = DecayScoring(repo)
        old = datetime.now(timezone.utc) - timedelta(days=30)
        score = scorer.compute_decay(old, lambda_val=0.05)
        # e^(-0.05 * 30) = e^(-1.5) ~ 0.223
        assert score < 0.3
        assert score > 0.1

    def test_compute_decay_with_access_count(self, repo: GraphRepository):
        """Access count should reduce the effective lambda, producing a higher score."""
        scorer = DecayScoring(repo)
        old = datetime.now(timezone.utc) - timedelta(days=30)
        lam = 0.05

        score_no_access = scorer.compute_decay(old, lam, access_count=0)
        score_with_access = scorer.compute_decay(old, lam, access_count=10)

        # With access_count=10, effective_lambda = 0.05 / (1 + log(11)) ≈ 0.015
        # Score should be higher (slower decay)
        assert score_with_access > score_no_access

        # Verify the formula: e^(-lam/(1+log(1+count)) * days)
        expected = exp(-lam / (1 + log(11)) * 30)
        assert score_with_access == pytest.approx(expected, abs=0.01)


class TestBatchUpdateScores:
    def test_batch_update_scores(self, repo: GraphRepository):
        """Insert nodes, run batch update, verify scores were updated."""
        scorer = DecayScoring(repo)

        # Node accessed 60 days ago -- should get a low score
        old_time = datetime.now(timezone.utc) - timedelta(days=60)
        nid_old = _insert_node(
            repo,
            title="Old Node",
            last_accessed=old_time,
            created_at=old_time,
            networks=["SOCIAL"],
        )

        # Node accessed just now -- should stay near 1.0
        nid_fresh = _insert_node(
            repo,
            title="Fresh Node",
            last_accessed=datetime.now(timezone.utc),
            networks=["PROFESSIONAL"],
        )

        count = scorer.batch_update_scores()
        assert count == 2

        # Check the old node's decay_score decreased
        row_old = repo._conn.execute(
            "SELECT decay_score FROM nodes WHERE id = ?", [nid_old]
        ).fetchone()
        assert row_old[0] < 0.5

        # Check the fresh node's decay_score is still high
        row_fresh = repo._conn.execute(
            "SELECT decay_score FROM nodes WHERE id = ?", [nid_fresh]
        ).fetchone()
        assert row_fresh[0] > 0.9

    def test_never_accessed_node_decays_from_created_at(self, repo: GraphRepository):
        """A node with last_accessed=None should decay from created_at, not stay at 1.0."""
        scorer = DecayScoring(repo)
        old_created = datetime.now(timezone.utc) - timedelta(days=30)

        nid = _insert_node(
            repo,
            title="Never Accessed",
            last_accessed=None,
            created_at=old_created,
            networks=["SOCIAL"],
        )

        scorer.batch_update_scores()

        row = repo._conn.execute(
            "SELECT decay_score FROM nodes WHERE id = ?", [nid]
        ).fetchone()
        assert row[0] < 1.0
        # SOCIAL lambda=0.07, 30 days → e^(-0.07*30) ≈ 0.12
        assert row[0] < 0.2

    def test_event_decays_from_event_date(self, repo: GraphRepository):
        """EVENT node should use event_date as anchor when it's more recent than created_at."""
        scorer = DecayScoring(repo)

        created = datetime.now(timezone.utc) - timedelta(days=60)
        event_date = datetime.now(timezone.utc) - timedelta(days=28)

        nid = _insert_node(
            repo,
            title="Past Conference",
            node_type="EVENT",
            created_at=created,
            last_accessed=None,
            properties={"event_date": event_date.isoformat()},
            networks=["PROFESSIONAL"],
        )

        scorer.batch_update_scores()

        row = repo._conn.execute(
            "SELECT decay_score FROM nodes WHERE id = ?", [nid]
        ).fetchone()
        # PROFESSIONAL lambda=0.03, 28 days from event_date → e^(-0.03*28) ≈ 0.43
        # If it used created_at (60 days) it would be e^(-0.03*60) ≈ 0.17
        assert row[0] > 0.3, "Should decay from event_date, not created_at"
        assert row[0] < 0.6

    def test_future_event_no_decay(self, repo: GraphRepository):
        """EVENT node with a future event_date should be pinned at 1.0."""
        scorer = DecayScoring(repo)

        future = datetime.now(timezone.utc) + timedelta(days=7)

        nid = _insert_node(
            repo,
            title="Upcoming Conference",
            node_type="EVENT",
            created_at=datetime.now(timezone.utc) - timedelta(days=30),
            last_accessed=None,
            properties={"event_date": future.isoformat()},
            networks=["PROFESSIONAL"],
        )

        scorer.batch_update_scores()

        row = repo._conn.execute(
            "SELECT decay_score FROM nodes WHERE id = ?", [nid]
        ).fetchone()
        assert row[0] == pytest.approx(1.0, abs=0.001)

    def test_open_commitment_no_decay(self, repo: GraphRepository):
        """COMMITMENT with status='open' should stay at 1.0 regardless of age."""
        scorer = DecayScoring(repo)

        nid = _insert_node(
            repo,
            title="Buy groceries",
            node_type="COMMITMENT",
            created_at=datetime.now(timezone.utc) - timedelta(days=90),
            last_accessed=None,
            properties={"status": "open"},
            networks=["PERSONAL_GROWTH"],
        )

        scorer.batch_update_scores()

        row = repo._conn.execute(
            "SELECT decay_score FROM nodes WHERE id = ?", [nid]
        ).fetchone()
        assert row[0] == pytest.approx(1.0, abs=0.001)

    def test_active_goal_no_decay(self, repo: GraphRepository):
        """GOAL with status='active' should stay at 1.0."""
        scorer = DecayScoring(repo)

        nid = _insert_node(
            repo,
            title="Learn Rust",
            node_type="GOAL",
            created_at=datetime.now(timezone.utc) - timedelta(days=60),
            last_accessed=None,
            properties={"status": "active"},
        )

        scorer.batch_update_scores()

        row = repo._conn.execute(
            "SELECT decay_score FROM nodes WHERE id = ?", [nid]
        ).fetchone()
        assert row[0] == pytest.approx(1.0, abs=0.001)

    def test_completed_commitment_decays(self, repo: GraphRepository):
        """COMMITMENT with status='completed' should decay normally."""
        scorer = DecayScoring(repo)

        nid = _insert_node(
            repo,
            title="Submit report",
            node_type="COMMITMENT",
            created_at=datetime.now(timezone.utc) - timedelta(days=60),
            last_accessed=None,
            properties={"status": "completed"},
            networks=["PROFESSIONAL"],
        )

        scorer.batch_update_scores()

        row = repo._conn.execute(
            "SELECT decay_score FROM nodes WHERE id = ?", [nid]
        ).fetchone()
        assert row[0] < 1.0
        # PROFESSIONAL lambda=0.03, 60 days → e^(-0.03*60) ≈ 0.17
        assert row[0] < 0.3

    def test_access_count_slows_decay(self, repo: GraphRepository):
        """A frequently accessed node should decay slower than a never-accessed one."""
        scorer = DecayScoring(repo)
        old = datetime.now(timezone.utc) - timedelta(days=30)

        nid_zero = _insert_node(
            repo,
            title="Rarely Seen",
            last_accessed=old,
            access_count=0,
            networks=["SOCIAL"],
        )

        nid_many = _insert_node(
            repo,
            title="Frequently Seen",
            last_accessed=old,
            access_count=10,
            networks=["SOCIAL"],
        )

        scorer.batch_update_scores()

        row_zero = repo._conn.execute(
            "SELECT decay_score FROM nodes WHERE id = ?", [nid_zero]
        ).fetchone()
        row_many = repo._conn.execute(
            "SELECT decay_score FROM nodes WHERE id = ?", [nid_many]
        ).fetchone()

        assert row_many[0] > row_zero[0], "Higher access_count should slow decay"


class TestGetDecayedNodes:
    def test_get_decayed_nodes(self, repo: GraphRepository):
        """Nodes below threshold should be returned; those above should not."""
        scorer = DecayScoring(repo)

        # Insert a node with an already-low decay_score
        nid_low = _insert_node(repo, title="Decayed Node", decay_score=0.1)
        # Insert a node with a high decay_score
        _insert_node(repo, title="Fresh Node", decay_score=0.9)

        decayed = scorer.get_decayed_nodes(threshold=0.3)
        assert len(decayed) == 1
        assert decayed[0]["id"] == nid_low
        assert decayed[0]["title"] == "Decayed Node"
