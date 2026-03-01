"""Unit tests for commitment scanning (Phase 5)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from memora.core.commitment_scan import CommitmentScanner
from memora.graph.repository import GraphRepository


def _insert_commitment(
    repo: GraphRepository,
    title: str = "Test Commitment",
    status: str = "open",
    due_date: str | None = None,
    networks: list[str] | None = None,
    deleted: bool = False,
) -> str:
    """Insert a COMMITMENT node directly into DuckDB."""
    nid = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    props: dict = {"status": status}
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
            title,
            "",
            f"hash_{nid[:8]}",
            json.dumps(props),
            1.0,
            networks or ["PROFESSIONAL"],
            False,
            0,
            1.0,
            [],
            now,
            now,
            deleted,
        ],
    )
    return nid


class TestScanEmptyGraph:
    def test_scan_empty_graph(self, repo: GraphRepository):
        """Scanning an empty graph should return empty overdue/approaching lists."""
        scanner = CommitmentScanner(repo)
        result = scanner.scan()

        assert result["overdue"] == []
        assert result["approaching"] == []
        assert result["stats"]["total_open"] == 0
        assert result["stats"]["overdue_count"] == 0
        assert result["stats"]["approaching_count"] == 0


class TestOverdueDetection:
    def test_overdue_detection(self, repo: GraphRepository):
        """A commitment with a past due_date should be flagged as overdue."""
        scanner = CommitmentScanner(repo)

        past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        nid = _insert_commitment(
            repo,
            title="Overdue Task",
            status="open",
            due_date=past,
        )

        result = scanner.scan()
        assert len(result["overdue"]) == 1
        assert result["overdue"][0]["node_id"] == nid
        assert result["overdue"][0]["title"] == "Overdue Task"
        assert result["overdue"][0]["days_overdue"] >= 4

    def test_completed_commitment_not_overdue(self, repo: GraphRepository):
        """A completed commitment with a past due_date should NOT appear."""
        scanner = CommitmentScanner(repo)

        past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        _insert_commitment(
            repo,
            title="Done Task",
            status="completed",
            due_date=past,
        )

        result = scanner.scan()
        assert len(result["overdue"]) == 0


class TestApproachingDeadline:
    def test_approaching_deadline(self, repo: GraphRepository):
        """A commitment due in 2 days should match the 3-day window."""
        scanner = CommitmentScanner(repo)

        future = (datetime.now(timezone.utc) + timedelta(days=2, hours=12)).isoformat()
        nid = _insert_commitment(
            repo,
            title="Approaching Task",
            status="open",
            due_date=future,
        )

        result = scanner.scan()
        assert len(result["approaching"]) == 1
        assert result["approaching"][0]["node_id"] == nid
        assert result["approaching"][0]["window_days"] == 3
        assert result["approaching"][0]["days_until_due"] <= 3

    def test_far_future_not_approaching(self, repo: GraphRepository):
        """A commitment due in 30 days should NOT appear in approaching."""
        scanner = CommitmentScanner(repo)

        far_future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        _insert_commitment(
            repo,
            title="Far Future Task",
            status="open",
            due_date=far_future,
        )

        result = scanner.scan()
        assert len(result["approaching"]) == 0
