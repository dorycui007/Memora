"""Unit tests for decay scoring (Phase 5)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
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
) -> str:
    """Helper to insert a raw node row directly into DuckDB."""
    nid = node_id or str(uuid4())
    now = datetime.utcnow().isoformat()
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
            json.dumps({}),
            1.0,
            networks or [],
            False,
            0,
            decay_score,
            [],
            now,
            now,
            last_accessed.isoformat() if last_accessed else None,
            deleted,
        ],
    )
    return nid


class TestComputeDecay:
    def test_compute_decay_fresh_node(self, repo: GraphRepository):
        """Decay should be ~1.0 for a node accessed just now."""
        scorer = DecayScoring(repo)
        now = datetime.utcnow()
        score = scorer.compute_decay(now, lambda_val=0.05)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_compute_decay_old_node(self, repo: GraphRepository):
        """Decay should decrease significantly for a node accessed long ago."""
        scorer = DecayScoring(repo)
        old = datetime.utcnow() - timedelta(days=30)
        score = scorer.compute_decay(old, lambda_val=0.05)
        # e^(-0.05 * 30) = e^(-1.5) ~ 0.223
        assert score < 0.3
        assert score > 0.1


class TestBatchUpdateScores:
    def test_batch_update_scores(self, repo: GraphRepository):
        """Insert nodes, run batch update, verify scores were updated."""
        scorer = DecayScoring(repo)

        # Node accessed 60 days ago -- should get a low score
        old_time = datetime.utcnow() - timedelta(days=60)
        nid_old = _insert_node(
            repo,
            title="Old Node",
            last_accessed=old_time,
            networks=["SOCIAL"],
        )

        # Node accessed just now -- should stay near 1.0
        nid_fresh = _insert_node(
            repo,
            title="Fresh Node",
            last_accessed=datetime.utcnow(),
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
