"""Unit tests for network health scoring (Phase 5)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from memora.core.health_scoring import HealthScoring
from memora.graph.repository import GraphRepository


def _insert_commitment(
    repo: GraphRepository,
    network: str = "PROFESSIONAL",
    status: str = "open",
    due_date: str | None = None,
    decay_score: float = 1.0,
) -> str:
    """Insert a COMMITMENT node with the given status and optional due_date."""
    nid = str(uuid4())
    now = datetime.utcnow().isoformat()
    props = {"status": status}
    if due_date:
        props["due_date"] = due_date
    repo._conn.execute(
        """INSERT INTO nodes
           (id, node_type, title, content, content_hash, properties,
            confidence, networks, human_approved, access_count,
            decay_score, tags, created_at, updated_at, deleted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            nid,
            "COMMITMENT",
            f"Commitment {nid[:6]}",
            "",
            f"hash_{nid[:8]}",
            json.dumps(props),
            1.0,
            [network],
            False,
            0,
            decay_score,
            [],
            now,
            now,
            False,
        ],
    )
    return nid


class TestDetermineStatus:
    def test_on_track_status(self):
        """High completion, low alerts, few stale nodes => on_track."""
        status = HealthScoring._determine_status(
            completion_rate=0.9,
            alert_ratio=0.0,
            staleness_flags=0,
        )
        assert status == "on_track"

    def test_needs_attention_status(self):
        """Medium completion rate => needs_attention."""
        status = HealthScoring._determine_status(
            completion_rate=0.5,
            alert_ratio=0.05,
            staleness_flags=0,
        )
        assert status == "needs_attention"

    def test_falling_behind_status(self):
        """Low completion rate => falling_behind."""
        status = HealthScoring._determine_status(
            completion_rate=0.2,
            alert_ratio=0.0,
            staleness_flags=0,
        )
        assert status == "falling_behind"

    def test_falling_behind_high_alerts(self):
        """High alert ratio also triggers falling_behind."""
        status = HealthScoring._determine_status(
            completion_rate=0.8,
            alert_ratio=0.5,
            staleness_flags=0,
        )
        assert status == "falling_behind"

    def test_falling_behind_staleness(self):
        """Many staleness flags triggers falling_behind."""
        status = HealthScoring._determine_status(
            completion_rate=0.8,
            alert_ratio=0.0,
            staleness_flags=3,
        )
        assert status == "falling_behind"


class TestDetermineMomentum:
    def test_momentum_stable_no_previous(self):
        """No previous snapshot => stable."""
        momentum = HealthScoring._determine_momentum(
            completion_rate=0.8,
            alert_ratio=0.1,
            previous=None,
        )
        assert momentum == "stable"

    def test_momentum_up(self):
        """Higher completion and lower alerts vs previous => up."""
        previous = {
            "commitment_completion_rate": 0.5,
            "alert_ratio": 0.2,
        }
        momentum = HealthScoring._determine_momentum(
            completion_rate=0.8,
            alert_ratio=0.1,
            previous=previous,
        )
        assert momentum == "up"

    def test_momentum_down(self):
        """Lower completion vs previous => down."""
        previous = {
            "commitment_completion_rate": 0.9,
            "alert_ratio": 0.0,
        }
        momentum = HealthScoring._determine_momentum(
            completion_rate=0.7,
            alert_ratio=0.1,
            previous=previous,
        )
        assert momentum == "down"

    def test_momentum_stable_similar(self):
        """Similar metrics vs previous => stable."""
        previous = {
            "commitment_completion_rate": 0.8,
            "alert_ratio": 0.1,
        }
        momentum = HealthScoring._determine_momentum(
            completion_rate=0.82,
            alert_ratio=0.1,
            previous=previous,
        )
        assert momentum == "stable"


class TestHealthScoringIntegration:
    def test_compute_network_health_empty(self, repo: GraphRepository):
        """An empty graph should produce on_track (no commitments = healthy)."""
        scorer = HealthScoring(repo)
        health = scorer.compute_network_health("PROFESSIONAL")
        assert health["status"] == "on_track"
        assert health["network"] == "PROFESSIONAL"
        assert health["commitment_completion_rate"] == 1.0

    def test_compute_network_health_with_commitments(self, repo: GraphRepository):
        """Insert some open and completed commitments, verify health status."""
        scorer = HealthScoring(repo)
        # 2 completed, 1 open => 2/3 ~ 0.67 completion => needs_attention
        _insert_commitment(repo, network="VENTURES", status="completed")
        _insert_commitment(repo, network="VENTURES", status="completed")
        _insert_commitment(repo, network="VENTURES", status="open")

        health = scorer.compute_network_health("VENTURES")
        assert health["commitment_completion_rate"] == pytest.approx(2.0 / 3.0, abs=0.01)
        # completion_rate ~0.67 falls in 0.4-0.7 range => needs_attention
        assert health["status"] == "needs_attention"
