"""Unit tests for gap detection (Phase 5)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from memora.core.gap_detection import GapDetector
from memora.graph.repository import GraphRepository


def _insert_node(
    repo: GraphRepository,
    node_id: str | None = None,
    node_type: str = "NOTE",
    title: str = "Test Node",
    properties: dict | None = None,
    networks: list[str] | None = None,
    created_at: str | None = None,
) -> str:
    """Insert a raw node row directly into DuckDB."""
    nid = node_id or str(uuid4())
    now = created_at or datetime.utcnow().isoformat()
    repo._conn.execute(
        """INSERT INTO nodes
           (id, node_type, title, content, content_hash, properties,
            confidence, networks, human_approved, access_count,
            decay_score, tags, created_at, updated_at, deleted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            nid,
            node_type,
            title,
            "",
            f"hash_{nid[:8]}",
            json.dumps(properties or {}),
            1.0,
            networks or [],
            False,
            0,
            1.0,
            [],
            now,
            now,
            False,
        ],
    )
    return nid


def _insert_edge(
    repo: GraphRepository,
    source_id: str,
    target_id: str,
    edge_type: str = "RELATED_TO",
    edge_category: str = "ASSOCIATIVE",
    created_at: str | None = None,
) -> str:
    """Insert a raw edge row directly into DuckDB."""
    eid = str(uuid4())
    now = created_at or datetime.utcnow().isoformat()
    repo._conn.execute(
        """INSERT INTO edges
           (id, source_id, target_id, edge_type, edge_category,
            properties, confidence, weight, bidirectional, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            eid,
            source_id,
            target_id,
            edge_type,
            edge_category,
            json.dumps({}),
            1.0,
            1.0,
            False,
            now,
            now,
        ],
    )
    return eid


class TestOrphanedNodes:
    def test_orphaned_nodes(self, repo: GraphRepository):
        """Nodes with no edges should be detected as orphaned."""
        detector = GapDetector(repo)

        # Insert two nodes with no edges
        nid1 = _insert_node(repo, title="Orphan A")
        nid2 = _insert_node(repo, title="Orphan B")

        # Insert a connected pair (should NOT appear)
        nid3 = _insert_node(repo, title="Connected C")
        nid4 = _insert_node(repo, title="Connected D")
        _insert_edge(repo, nid3, nid4)

        results = detector.detect_all()
        orphans = results["orphaned_nodes"]
        orphan_ids = {o["id"] for o in orphans}

        assert nid1 in orphan_ids
        assert nid2 in orphan_ids
        assert nid3 not in orphan_ids
        assert nid4 not in orphan_ids


class TestUnresolvedDecisions:
    def test_unresolved_decisions(self, repo: GraphRepository):
        """DECISION nodes with no outcome should be detected."""
        detector = GapDetector(repo)

        # Decision with no outcome
        nid_unresolved = _insert_node(
            repo,
            node_type="DECISION",
            title="Unresolved Decision",
            properties={"options_considered": ["A", "B"]},
        )

        # Decision with an outcome (should NOT appear)
        _insert_node(
            repo,
            node_type="DECISION",
            title="Resolved Decision",
            properties={"options_considered": ["X", "Y"], "outcome": "Chose X"},
        )

        results = detector.detect_all()
        unresolved = results["unresolved_decisions"]
        unresolved_ids = {u["id"] for u in unresolved}

        assert nid_unresolved in unresolved_ids
        assert len(unresolved) == 1


class TestEmptyGraph:
    def test_empty_graph(self, repo: GraphRepository):
        """An empty graph should return empty lists for all gap categories."""
        detector = GapDetector(repo)
        results = detector.detect_all()

        assert results["orphaned_nodes"] == []
        assert results["stalled_goals"] == []
        assert results["dead_end_projects"] == []
        assert results["isolated_concepts"] == []
        assert results["unresolved_decisions"] == []
