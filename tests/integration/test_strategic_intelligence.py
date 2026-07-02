"""Integration tests for Memora 2.0 strategic intelligence features.

Tests the full chain: seed data → position tracking → briefing → deadlines → patterns.
Uses in-memory DuckDB (no LLM calls required).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from memora.graph.models import (
    BaseNode,
    Edge,
    EdgeCategory,
    EdgeType,
    NetworkType,
    NodeType,
    parse_properties,
)
from memora.graph.repository import GraphRepository, YOU_NODE_ID


@pytest.fixture
def repo():
    """Create an in-memory GraphRepository with seeded strategic data."""
    r = GraphRepository(None)

    # ── Create organizations ──
    mcss = BaseNode(
        node_type=NodeType.ORGANIZATION,
        title="MCSS",
        properties={"name": "MCSS", "org_type": "student society"},
        networks=[NetworkType.CLUBS],
        confidence=1.0,
    )
    mcss.compute_content_hash()
    mcss_id = r.create_node(mcss)

    utmist = BaseNode(
        node_type=NodeType.ORGANIZATION,
        title="UTMIST",
        properties={"name": "UTMIST", "org_type": "student society"},
        networks=[NetworkType.CLUBS],
        confidence=1.0,
    )
    utmist.compute_content_hash()
    utmist_id = r.create_node(utmist)

    # ── Create positions ──
    vp_tech = BaseNode(
        node_type=NodeType.POSITION,
        title="VP Technology — MCSS",
        properties={
            "title": "VP Technology",
            "organization": "MCSS",
            "status": "active",
            "time_hrs_week": 8.0,
            "blockers": ["website migration", "budget approval"],
        },
        networks=[NetworkType.CLUBS],
        confidence=1.0,
    )
    vp_tech.compute_content_hash()
    vp_id = r.create_node(vp_tech)

    assoc_dir = BaseNode(
        node_type=NodeType.POSITION,
        title="Associate Director — UTMIST",
        properties={
            "title": "Associate Director",
            "organization": "UTMIST",
            "status": "active",
        },
        networks=[NetworkType.CLUBS],
        confidence=1.0,
    )
    assoc_dir.compute_content_hash()
    ad_id = r.create_node(assoc_dir)

    # ── HOLDS_POSITION edges ──
    r.create_edge(Edge(
        source_id=YOU_NODE_ID,
        target_id=vp_id,
        edge_type=EdgeType.HOLDS_POSITION,
        edge_category=EdgeCategory.STRATEGIC,
        confidence=1.0,
    ))
    r.create_edge(Edge(
        source_id=YOU_NODE_ID,
        target_id=ad_id,
        edge_type=EdgeType.HOLDS_POSITION,
        edge_category=EdgeCategory.STRATEGIC,
        confidence=1.0,
    ))

    # ── MEMBER_OF edges ──
    r.create_edge(Edge(
        source_id=vp_id,
        target_id=mcss_id,
        edge_type=EdgeType.MEMBER_OF,
        edge_category=EdgeCategory.NETWORK,
        confidence=1.0,
    ))

    # ── Create commitments linked to VP Tech ──
    now = datetime.now(timezone.utc)
    overdue_commit = BaseNode(
        node_type=NodeType.COMMITMENT,
        title="Fix MCSS website deployment",
        properties={
            "status": "overdue",
            "due_date": (now - timedelta(days=3)).isoformat(),
            "priority": "high",
        },
        networks=[NetworkType.CLUBS],
        confidence=0.9,
    )
    overdue_commit.compute_content_hash()
    oc_id = r.create_node(overdue_commit)
    r.create_edge(Edge(
        source_id=oc_id,
        target_id=vp_id,
        edge_type=EdgeType.RELATED_TO,
        edge_category=EdgeCategory.ASSOCIATIVE,
        confidence=0.9,
    ))

    upcoming_commit = BaseNode(
        node_type=NodeType.COMMITMENT,
        title="Prepare DeerHacks workshop slides",
        properties={
            "status": "open",
            "due_date": (now + timedelta(days=5)).isoformat(),
            "priority": "medium",
        },
        networks=[NetworkType.CLUBS],
        confidence=0.9,
    )
    upcoming_commit.compute_content_hash()
    uc_id = r.create_node(upcoming_commit)
    r.create_edge(Edge(
        source_id=uc_id,
        target_id=vp_id,
        edge_type=EdgeType.RELATED_TO,
        edge_category=EdgeCategory.ASSOCIATIVE,
        confidence=0.9,
    ))

    # ── Create a person connected to both positions (flywheel) ──
    person = BaseNode(
        node_type=NodeType.PERSON,
        title="Emily Su",
        properties={"name": "Emily Su", "role": "President, MCSS"},
        networks=[NetworkType.CLUBS, NetworkType.SOCIAL],
        confidence=1.0,
    )
    person.compute_content_hash()
    person_id = r.create_node(person)
    r.create_edge(Edge(
        source_id=person_id,
        target_id=vp_id,
        edge_type=EdgeType.COLLABORATES_WITH,
        edge_category=EdgeCategory.SOCIAL,
        confidence=0.9,
    ))
    r.create_edge(Edge(
        source_id=person_id,
        target_id=ad_id,
        edge_type=EdgeType.COLLABORATES_WITH,
        edge_category=EdgeCategory.SOCIAL,
        confidence=0.8,
    ))
    r.create_edge(Edge(
        source_id=YOU_NODE_ID,
        target_id=person_id,
        edge_type=EdgeType.KNOWS,
        edge_category=EdgeCategory.SOCIAL,
        confidence=1.0,
    ))

    # ── Create courses ──
    csc108 = BaseNode(
        node_type=NodeType.COURSE,
        title="CSC108 — Intro to Programming",
        properties={
            "code": "CSC108",
            "name": "Introduction to Computer Programming",
            "semester": "Fall 2024",
            "status": "completed",
            "grade": "A",
            "credits": 0.5,
        },
        networks=[NetworkType.ACADEMIC],
        confidence=1.0,
    )
    csc108.compute_content_hash()
    csc108_id = r.create_node(csc108)

    csc148 = BaseNode(
        node_type=NodeType.COURSE,
        title="CSC148 — Intro to CS",
        properties={
            "code": "CSC148",
            "name": "Introduction to Computer Science",
            "semester": "Winter 2025",
            "status": "completed",
            "grade": "A",
            "credits": 0.5,
        },
        networks=[NetworkType.ACADEMIC],
        confidence=1.0,
    )
    csc148.compute_content_hash()
    csc148_id = r.create_node(csc148)

    # PREREQUISITE_OF edge
    r.create_edge(Edge(
        source_id=csc108_id,
        target_id=csc148_id,
        edge_type=EdgeType.PREREQUISITE_OF,
        edge_category=EdgeCategory.STRUCTURAL,
        confidence=1.0,
    ))

    # ── Create election ──
    election = BaseNode(
        node_type=NodeType.ELECTION,
        title="MCSS VP Technology Election 2026",
        properties={
            "position_title": "VP Technology",
            "organization": "MCSS",
            "date": (now + timedelta(days=30)).isoformat(),
            "result": "pending",
            "candidates": ["Ericsson Cui", "Jane Doe"],
        },
        networks=[NetworkType.CLUBS, NetworkType.GOVERNANCE],
        confidence=1.0,
    )
    election.compute_content_hash()
    election_id = r.create_node(election)
    r.create_edge(Edge(
        source_id=YOU_NODE_ID,
        target_id=election_id,
        edge_type=EdgeType.CANDIDATE_IN,
        edge_category=EdgeCategory.STRATEGIC,
        confidence=1.0,
    ))

    yield r
    r.close()


class TestPositionTracker:
    def test_get_all_positions(self, repo):
        from memora.core.position_tracker import PositionTracker

        tracker = PositionTracker(repo)
        positions = tracker.get_all_positions()

        assert len(positions) == 2
        vp = next(p for p in positions if "VP Technology" in p["title"])
        assert vp["organization"] == "MCSS"
        assert vp["status"] == "active"
        assert len(vp["blockers"]) == 2
        assert vp["commitment_count"] >= 1

    def test_position_health(self, repo):
        from memora.core.position_tracker import PositionTracker

        tracker = PositionTracker(repo)
        positions = tracker.get_all_positions()

        vp = next(p for p in positions if "VP Technology" in p["title"])
        # Has overdue commitments, so health should be < 1.0
        assert vp["health"] < 1.0
        assert vp["overdue_commitments"] >= 1

    def test_flywheel_detection(self, repo):
        from memora.core.position_tracker import PositionTracker

        tracker = PositionTracker(repo)
        flywheels = tracker.detect_flywheels()

        # Emily Su is connected to both positions
        assert len(flywheels) >= 1
        fw = flywheels[0]
        assert fw["shared_entities"] >= 1

    def test_position_detail(self, repo):
        from memora.core.position_tracker import PositionTracker
        from memora.graph.models import NodeFilter, NodeType

        tracker = PositionTracker(repo)
        positions = repo.query_nodes(NodeFilter(node_types=[NodeType.POSITION], limit=10))
        vp = next(p for p in positions if "VP Technology" in p.title)

        detail = tracker.get_position_detail(str(vp.id))
        assert detail is not None
        assert detail["title"] == "VP Technology — MCSS"
        assert len(detail["commitments"]) >= 1


class TestAcademicTracker:
    def test_get_roadmap(self, repo):
        from memora.core.academic_tracker import AcademicTracker

        tracker = AcademicTracker(repo)
        roadmap = tracker.get_roadmap()

        assert len(roadmap["courses"]) == 2
        assert roadmap["stats"]["completed"] == 2

    def test_compute_gpa(self, repo):
        from memora.core.academic_tracker import AcademicTracker

        tracker = AcademicTracker(repo)
        gpa = tracker.compute_gpa()

        # Both courses have grade A (4.0)
        assert gpa["cumulative_gpa"] == 4.0
        assert gpa["total_credits"] == 1.0

    def test_prerequisite_chain(self, repo):
        from memora.core.academic_tracker import AcademicTracker
        from memora.graph.models import NodeFilter, NodeType

        tracker = AcademicTracker(repo)
        courses = repo.query_nodes(NodeFilter(node_types=[NodeType.COURSE], limit=10))
        csc148 = next(c for c in courses if "CSC148" in c.title)

        chain = tracker.get_prerequisite_chain(str(csc148.id))
        assert len(chain) == 1
        assert chain[0]["code"] == "CSC108"


class TestDeadlineManager:
    def test_get_upcoming(self, repo):
        from memora.core.deadline_manager import DeadlineManager

        manager = DeadlineManager(repo)
        deadlines = manager.get_upcoming(days=30)

        # Should include the upcoming commitment and the election
        assert len(deadlines) >= 2

    def test_get_critical(self, repo):
        from memora.core.deadline_manager import DeadlineManager

        manager = DeadlineManager(repo)
        critical = manager.get_critical()

        # The overdue commitment should appear
        overdue = [d for d in critical if d["overdue"]]
        assert len(overdue) >= 1


class TestElectionIntel:
    def test_get_elections(self, repo):
        from memora.core.election_intel import ElectionIntel

        intel = ElectionIntel(repo)
        elections = intel.get_elections()

        assert len(elections) == 1
        e = elections[0]
        assert e["position_title"] == "VP Technology"
        assert e["result"] == "pending"
        assert e["candidate_count"] >= 1

    def test_endorsement_graph(self, repo):
        from memora.core.election_intel import ElectionIntel
        from memora.graph.models import NodeFilter, NodeType

        intel = ElectionIntel(repo)
        elections = repo.query_nodes(NodeFilter(node_types=[NodeType.ELECTION], limit=10))
        e = elections[0]

        graph = intel.get_endorsement_graph(str(e.id))
        assert len(graph["nodes"]) >= 1
        assert graph["nodes"][0]["type"] == "ELECTION"


class TestBriefingCollector:
    def test_collect_includes_positions(self, repo):
        from memora.core.briefing import BriefingCollector

        collector = BriefingCollector(repo)
        data = collector.collect()

        assert "positions" in data
        assert len(data["positions"]) == 2

    def test_collect_includes_deadlines(self, repo):
        from memora.core.briefing import BriefingCollector

        collector = BriefingCollector(repo)
        data = collector.collect()

        assert "deadlines" in data
        assert len(data["deadlines"]) >= 1


class TestOntologyValidation:
    def test_new_node_types_valid(self, repo):
        """Verify new node types can be created and queried."""
        from memora.graph.models import NodeFilter

        for ntype in [NodeType.ORGANIZATION, NodeType.POSITION, NodeType.ELECTION,
                      NodeType.COURSE, NodeType.METRIC]:
            filters = NodeFilter(node_types=[ntype], limit=10)
            # Should not raise
            repo.query_nodes(filters)

    def test_new_edge_types_valid(self, repo):
        """Verify new edge types are correctly constrained."""
        from memora.graph.ontology import validate_edge

        # Valid edges
        assert validate_edge(NodeType.PERSON, NodeType.POSITION, EdgeType.HOLDS_POSITION)
        assert validate_edge(NodeType.PERSON, NodeType.ELECTION, EdgeType.CANDIDATE_IN)
        assert validate_edge(NodeType.COURSE, NodeType.COURSE, EdgeType.PREREQUISITE_OF)
        assert validate_edge(NodeType.METRIC, NodeType.GOAL, EdgeType.MEASURES)

        # Invalid edges
        assert not validate_edge(NodeType.EVENT, NodeType.POSITION, EdgeType.HOLDS_POSITION)
        assert not validate_edge(NodeType.NOTE, NodeType.ELECTION, EdgeType.CANDIDATE_IN)

    def test_member_of_accepts_organization(self, repo):
        """MEMBER_OF target should now include ORGANIZATION."""
        from memora.graph.ontology import validate_edge

        assert validate_edge(NodeType.PERSON, NodeType.ORGANIZATION, EdgeType.MEMBER_OF)
        assert validate_edge(NodeType.POSITION, NodeType.ORGANIZATION, EdgeType.MEMBER_OF)


class TestGetEdgesByType:
    def test_get_edges_by_type(self, repo):
        """Verify the new get_edges_by_type method works."""
        edges = repo.get_edges_by_type("HOLDS_POSITION")
        assert len(edges) == 2

        edges = repo.get_edges_by_type("CANDIDATE_IN")
        assert len(edges) == 1

        edges = repo.get_edges_by_type("NONEXISTENT")
        assert len(edges) == 0
