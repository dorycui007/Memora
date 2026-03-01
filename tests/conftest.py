"""Shared test fixtures for Memora backend tests."""

from __future__ import annotations

import pytest

from memora.graph.models import (
    BaseNode,
    Capture,
    CommitmentNode,
    Edge,
    EdgeCategory,
    EdgeType,
    EventNode,
    GoalNode,
    GraphProposal,
    NetworkType,
    NodeProposal,
    NodeType,
    PersonNode,
    EdgeProposal,
)
from memora.graph.repository import GraphRepository


@pytest.fixture
def repo():
    """In-memory DuckDB repository for testing."""
    r = GraphRepository(db_path=None)
    yield r
    r.close()


@pytest.fixture
def sample_person() -> PersonNode:
    return PersonNode(
        title="Sam Chen",
        content="Sam is a friend and investor contact",
        name="Sam Chen",
        role="Investor",
        relationship_to_user="friend",
        networks=[NetworkType.SOCIAL, NetworkType.VENTURES],
        confidence=0.9,
        proposed_by="archivist",
    )


@pytest.fixture
def sample_event() -> EventNode:
    return EventNode(
        title="Coffee with Sam",
        content="Met Sam at Blue Bottle to discuss investment opportunity",
        event_type="meeting",
        location="Blue Bottle Coffee",
        participants=["Sam Chen"],
        networks=[NetworkType.VENTURES],
        confidence=0.85,
        proposed_by="archivist",
    )


@pytest.fixture
def sample_commitment() -> CommitmentNode:
    return CommitmentNode(
        title="Send pitch deck to Sam",
        content="Promised to send the updated pitch deck by Friday",
        committed_by="user",
        committed_to="Sam Chen",
        networks=[NetworkType.VENTURES],
        confidence=0.9,
        proposed_by="archivist",
    )


@pytest.fixture
def sample_capture() -> Capture:
    return Capture(
        raw_content="Had coffee with Sam Chen today. He wants to see our pitch deck by Friday.",
        modality="text",
    )


@pytest.fixture
def sample_graph_proposal(sample_capture: Capture) -> GraphProposal:
    return GraphProposal(
        source_capture_id=str(sample_capture.id),
        confidence=0.88,
        nodes_to_create=[
            NodeProposal(
                temp_id="person_1",
                node_type=NodeType.PERSON,
                title="Sam Chen",
                content="Investor contact",
                properties={"name": "Sam Chen", "role": "Investor"},
                confidence=0.9,
                networks=[NetworkType.VENTURES],
            ),
            NodeProposal(
                temp_id="event_1",
                node_type=NodeType.EVENT,
                title="Coffee with Sam",
                content="Met at Blue Bottle",
                properties={"location": "Blue Bottle Coffee"},
                confidence=0.85,
                networks=[NetworkType.VENTURES],
            ),
        ],
        edges_to_create=[
            EdgeProposal(
                source_id="person_1",
                target_id="event_1",
                edge_type=EdgeType.RELATED_TO,
                edge_category=EdgeCategory.ASSOCIATIVE,
                confidence=0.85,
            ),
        ],
        human_summary="Adding Sam Chen and coffee meeting event",
    )
