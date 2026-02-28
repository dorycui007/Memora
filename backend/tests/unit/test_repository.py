"""Tests for GraphRepository — CRUD operations on in-memory DuckDB."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from memora.graph.models import (
    Capture,
    CommitmentNode,
    Edge,
    EdgeCategory,
    EdgeType,
    EventNode,
    GraphProposal,
    EdgeProposal,
    NetworkType,
    NodeFilter,
    NodeProposal,
    NodeType,
    PersonNode,
    ProposalRoute,
    ProposalStatus,
)
from memora.graph.repository import GraphRepository


class TestCapturesCRUD:
    def test_create_and_get_capture(self, repo: GraphRepository):
        c = Capture(raw_content="Test capture content", modality="text")
        cid = repo.create_capture(c)
        assert isinstance(cid, UUID)

        retrieved = repo.get_capture(cid)
        assert retrieved is not None
        assert retrieved.raw_content == "Test capture content"
        assert len(retrieved.content_hash) == 64

    def test_duplicate_capture_rejected(self, repo: GraphRepository):
        c1 = Capture(raw_content="Same content")
        repo.create_capture(c1)
        assert repo.check_capture_exists(c1.content_hash)

    def test_nonexistent_capture_returns_none(self, repo: GraphRepository):
        assert repo.get_capture(uuid4()) is None


class TestNodesCRUD:
    def test_create_and_get_node(self, repo: GraphRepository, sample_person: PersonNode):
        nid = repo.create_node(sample_person)
        assert isinstance(nid, UUID)

        node = repo.get_node(nid)
        assert node is not None
        assert node.title == "Sam Chen"
        assert isinstance(node, PersonNode)

    def test_update_node(self, repo: GraphRepository, sample_person: PersonNode):
        nid = repo.create_node(sample_person)
        updated = repo.update_node(nid, {"title": "Samuel Chen", "confidence": 0.95})
        assert updated is not None
        assert updated.title == "Samuel Chen"

    def test_soft_delete_node(self, repo: GraphRepository, sample_person: PersonNode):
        nid = repo.create_node(sample_person)
        repo.delete_node(nid)
        assert repo.get_node(nid) is None

    def test_query_nodes_by_type(self, repo: GraphRepository, sample_person, sample_event):
        repo.create_node(sample_person)
        repo.create_node(sample_event)

        persons = repo.query_nodes(NodeFilter(node_types=[NodeType.PERSON]))
        assert len(persons) == 1
        assert persons[0].title == "Sam Chen"

        events = repo.query_nodes(NodeFilter(node_types=[NodeType.EVENT]))
        assert len(events) == 1

    def test_query_nodes_by_network(self, repo: GraphRepository, sample_person, sample_event):
        repo.create_node(sample_person)
        repo.create_node(sample_event)

        social = repo.query_nodes(NodeFilter(networks=[NetworkType.SOCIAL]))
        assert len(social) == 1  # only sample_person has SOCIAL

        ventures = repo.query_nodes(NodeFilter(networks=[NetworkType.VENTURES]))
        assert len(ventures) == 2  # both have VENTURES

    def test_query_nodes_with_confidence_filter(self, repo: GraphRepository):
        node_high = PersonNode(
            title="High", name="High", confidence=0.95,
            networks=[NetworkType.SOCIAL], proposed_by="test",
        )
        node_low = PersonNode(
            title="Low", name="Low", confidence=0.5,
            networks=[NetworkType.SOCIAL], proposed_by="test",
        )
        repo.create_node(node_high)
        repo.create_node(node_low)

        results = repo.query_nodes(NodeFilter(min_confidence=0.8))
        assert len(results) == 1
        assert results[0].title == "High"


class TestEdgesCRUD:
    def test_create_and_get_edges(self, repo: GraphRepository, sample_person, sample_event):
        pid = repo.create_node(sample_person)
        eid = repo.create_node(sample_event)

        edge = Edge(
            source_id=pid,
            target_id=eid,
            edge_type=EdgeType.RELATED_TO,
            edge_category=EdgeCategory.ASSOCIATIVE,
            confidence=0.85,
        )
        edge_id = repo.create_edge(edge)
        assert isinstance(edge_id, UUID)

        edges = repo.get_edges(pid, direction="outgoing")
        assert len(edges) == 1
        assert edges[0].edge_type == EdgeType.RELATED_TO

    def test_get_edges_both_directions(self, repo: GraphRepository, sample_person, sample_event):
        pid = repo.create_node(sample_person)
        eid = repo.create_node(sample_event)

        edge = Edge(
            source_id=pid, target_id=eid,
            edge_type=EdgeType.KNOWS, edge_category=EdgeCategory.SOCIAL,
        )
        repo.create_edge(edge)

        assert len(repo.get_edges(pid, "outgoing")) == 1
        assert len(repo.get_edges(pid, "incoming")) == 0
        assert len(repo.get_edges(eid, "incoming")) == 1
        assert len(repo.get_edges(pid, "both")) == 1


class TestNeighborhood:
    def test_1_hop_neighborhood(self, repo: GraphRepository):
        p1 = PersonNode(title="A", name="A", networks=[NetworkType.SOCIAL], proposed_by="test")
        p2 = PersonNode(title="B", name="B", networks=[NetworkType.SOCIAL], proposed_by="test")
        p3 = PersonNode(title="C", name="C", networks=[NetworkType.SOCIAL], proposed_by="test")

        id1 = repo.create_node(p1)
        id2 = repo.create_node(p2)
        id3 = repo.create_node(p3)

        repo.create_edge(Edge(
            source_id=id1, target_id=id2,
            edge_type=EdgeType.KNOWS, edge_category=EdgeCategory.SOCIAL,
        ))
        repo.create_edge(Edge(
            source_id=id2, target_id=id3,
            edge_type=EdgeType.KNOWS, edge_category=EdgeCategory.SOCIAL,
        ))

        sub = repo.get_neighborhood(id1, hops=1)
        node_ids = {str(n.id) for n in sub.nodes}
        assert str(id1) in node_ids
        assert str(id2) in node_ids
        # id3 is 2 hops away, should NOT be in 1-hop
        assert str(id3) not in node_ids


class TestProposals:
    def test_create_and_commit_proposal(self, repo: GraphRepository, sample_capture, sample_graph_proposal):
        # Store the capture first
        repo.create_capture(sample_capture)

        # Create proposal
        proposal_id = repo.create_proposal(sample_graph_proposal)
        assert isinstance(proposal_id, UUID)

        # Verify it's pending
        pending = repo.get_pending_proposals()
        assert len(pending) == 1

        # Commit
        success = repo.commit_proposal(proposal_id)
        assert success is True

        # Nodes should now exist
        all_nodes = repo.query_nodes(NodeFilter())
        assert len(all_nodes) == 2  # person + event

        # Edges should exist
        person_nodes = repo.query_nodes(NodeFilter(node_types=[NodeType.PERSON]))
        assert len(person_nodes) == 1
        edges = repo.get_edges(person_nodes[0].id)
        assert len(edges) == 1

    def test_proposal_rejection(self, repo: GraphRepository, sample_capture, sample_graph_proposal):
        repo.create_capture(sample_capture)
        proposal_id = repo.create_proposal(sample_graph_proposal)
        repo.update_proposal_status(proposal_id, ProposalStatus.REJECTED, "human")

        pending = repo.get_pending_proposals()
        assert len(pending) == 0


class TestGraphStats:
    def test_empty_stats(self, repo: GraphRepository):
        stats = repo.get_graph_stats()
        assert stats["node_count"] == 0
        assert stats["edge_count"] == 0

    def test_stats_after_inserts(self, repo: GraphRepository, sample_person, sample_event):
        repo.create_node(sample_person)
        repo.create_node(sample_event)

        stats = repo.get_graph_stats()
        assert stats["node_count"] == 2
        assert stats["type_breakdown"]["PERSON"] == 1
        assert stats["type_breakdown"]["EVENT"] == 1
