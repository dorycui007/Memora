"""Tests for Pydantic domain models — serialization, validation, content hashing."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest

from memora.graph.models import (
    BaseNode,
    Capture,
    CommitmentNode,
    CommitmentStatus,
    ConceptNode,
    DecisionNode,
    Edge,
    EdgeCategory,
    EdgeProposal,
    EdgeType,
    EdgeUpdate,
    EventNode,
    FinancialDirection,
    FinancialItemNode,
    GoalNode,
    GoalStatus,
    GraphProposal,
    IdeaMaturity,
    IdeaNode,
    InsightNode,
    NetworkAssignment,
    NetworkType,
    NodeFilter,
    NodeProposal,
    NodeType,
    NodeUpdate,
    NoteNode,
    NoteType,
    PersonNode,
    Priority,
    ProjectNode,
    ProjectStatus,
    ReferenceNode,
    Subgraph,
    TemporalAnchor,
    NODE_TYPE_MODEL_MAP,
)


class TestEnums:
    def test_node_type_has_12_members(self):
        assert len(NodeType) == 12

    def test_edge_category_has_7_members(self):
        assert len(EdgeCategory) == 7

    def test_edge_type_has_29_members(self):
        assert len(EdgeType) == 29

    def test_network_type_has_7_members(self):
        assert len(NetworkType) == 7

    def test_enum_string_values(self):
        assert NodeType.EVENT == "EVENT"
        assert EdgeCategory.STRUCTURAL == "STRUCTURAL"
        assert NetworkType.ACADEMIC == "ACADEMIC"


class TestBaseNode:
    def test_create_base_node(self):
        node = BaseNode(node_type=NodeType.EVENT, title="Test")
        assert isinstance(node.id, UUID)
        assert node.node_type == NodeType.EVENT
        assert node.confidence == 1.0
        assert node.decay_score == 1.0
        assert node.human_approved is False

    def test_content_hash(self):
        node = BaseNode(node_type=NodeType.NOTE, title="Title", content="Content")
        h = node.compute_content_hash()
        assert len(h) == 64
        assert node.content_hash == h

    def test_serialization_roundtrip(self):
        node = PersonNode(
            title="Alice",
            name="Alice Smith",
            role="Engineer",
            networks=[NetworkType.PROFESSIONAL],
        )
        data = node.model_dump(mode="json")
        assert data["node_type"] == "PERSON"
        assert data["name"] == "Alice Smith"
        # Round-trip
        restored = PersonNode(**data)
        assert restored.name == "Alice Smith"
        assert restored.networks == [NetworkType.PROFESSIONAL]


class TestTypedNodes:
    def test_event_node(self):
        n = EventNode(title="Meeting", event_type="standup", participants=["Alice"])
        assert n.node_type == NodeType.EVENT
        assert n.participants == ["Alice"]

    def test_person_node(self):
        n = PersonNode(title="Bob", name="Bob", aliases=["Robert"])
        assert n.node_type == NodeType.PERSON
        assert n.aliases == ["Robert"]

    def test_commitment_node(self):
        n = CommitmentNode(title="Submit report", priority=Priority.HIGH)
        assert n.status == CommitmentStatus.OPEN
        assert n.priority == Priority.HIGH

    def test_decision_node(self):
        n = DecisionNode(
            title="Choose DB",
            options_considered=["Postgres", "DuckDB"],
            chosen_option="DuckDB",
        )
        assert n.reversible is True

    def test_goal_node(self):
        n = GoalNode(title="Run marathon", progress=0.3)
        assert n.status == GoalStatus.ACTIVE
        assert n.progress == 0.3

    def test_financial_item_node(self):
        n = FinancialItemNode(title="Rent", amount=2000, direction=FinancialDirection.OUTFLOW)
        assert n.currency == "USD"

    def test_note_node(self):
        n = NoteNode(title="Observation", note_type=NoteType.REFLECTION)
        assert n.note_type == NoteType.REFLECTION

    def test_idea_node(self):
        n = IdeaNode(title="New feature", maturity=IdeaMaturity.SEED)
        assert n.maturity == IdeaMaturity.SEED

    def test_project_node(self):
        n = ProjectNode(title="Memora", status=ProjectStatus.ACTIVE)
        assert n.deliverables == []

    def test_concept_node(self):
        n = ConceptNode(title="Graph Theory", definition="Study of graphs")
        assert n.complexity_level.value == "basic"

    def test_reference_node(self):
        n = ReferenceNode(title="Paper", url="https://example.com")
        assert n.archived is False

    def test_insight_node(self):
        n = InsightNode(title="Key insight", actionable=True, cross_network=True)
        assert n.strength == 0.5

    def test_node_type_model_map_complete(self):
        for nt in NodeType:
            assert nt in NODE_TYPE_MODEL_MAP


class TestEdge:
    def test_create_edge(self):
        from uuid import uuid4
        e = Edge(
            source_id=uuid4(),
            target_id=uuid4(),
            edge_type=EdgeType.RELATED_TO,
            edge_category=EdgeCategory.ASSOCIATIVE,
        )
        assert isinstance(e.id, UUID)
        assert e.weight == 1.0
        assert e.bidirectional is False

    def test_edge_serialization(self):
        from uuid import uuid4
        e = Edge(
            source_id=uuid4(),
            target_id=uuid4(),
            edge_type=EdgeType.KNOWS,
            edge_category=EdgeCategory.SOCIAL,
            confidence=0.8,
        )
        data = e.model_dump(mode="json")
        assert data["edge_type"] == "KNOWS"
        restored = Edge(**data)
        assert restored.edge_type == EdgeType.KNOWS


class TestPipelineModels:
    def test_temporal_anchor(self):
        ta = TemporalAnchor(temporal_type="future")
        assert ta.occurred_at is None

    def test_node_proposal(self):
        np = NodeProposal(
            temp_id="t1",
            node_type=NodeType.PERSON,
            title="Test",
            confidence=0.9,
        )
        assert np.networks == []

    def test_graph_proposal(self):
        gp = GraphProposal(
            source_capture_id="test-capture",
            confidence=0.85,
            nodes_to_create=[
                NodeProposal(
                    temp_id="t1",
                    node_type=NodeType.EVENT,
                    title="Event",
                )
            ],
        )
        assert len(gp.nodes_to_create) == 1
        assert gp.edges_to_create == []

    def test_graph_proposal_serialization(self):
        gp = GraphProposal(
            source_capture_id="c1",
            nodes_to_create=[
                NodeProposal(temp_id="t1", node_type=NodeType.NOTE, title="Note")
            ],
            edges_to_create=[
                EdgeProposal(
                    source_id="t1",
                    target_id="existing-id",
                    edge_type=EdgeType.RELATED_TO,
                    edge_category=EdgeCategory.ASSOCIATIVE,
                )
            ],
        )
        data = gp.model_dump(mode="json")
        restored = GraphProposal(**data)
        assert len(restored.nodes_to_create) == 1
        assert len(restored.edges_to_create) == 1


class TestCapture:
    def test_create_capture(self):
        c = Capture(raw_content="Hello world")
        assert isinstance(c.id, UUID)
        assert c.modality == "text"

    def test_capture_content_hash(self):
        c = Capture(raw_content="Test content")
        h = c.compute_content_hash()
        assert len(h) == 64
        # Same content = same hash
        c2 = Capture(raw_content="Test content")
        assert c2.compute_content_hash() == h


class TestNodeFilter:
    def test_default_filter(self):
        f = NodeFilter()
        assert f.limit == 50
        assert f.offset == 0

    def test_filter_with_types(self):
        f = NodeFilter(
            node_types=[NodeType.PERSON, NodeType.EVENT],
            networks=[NetworkType.SOCIAL],
        )
        assert len(f.node_types) == 2


class TestConfidenceValidation:
    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            BaseNode(node_type=NodeType.EVENT, title="Test", confidence=1.5)

        with pytest.raises(Exception):
            BaseNode(node_type=NodeType.EVENT, title="Test", confidence=-0.1)
