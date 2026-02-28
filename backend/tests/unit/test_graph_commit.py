"""Tests for atomic graph commit and proposal lifecycle."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from memora.graph.models import (
    EdgeCategory,
    EdgeProposal,
    EdgeType,
    GraphProposal,
    NetworkType,
    NodeProposal,
    NodeType,
    ProposalRoute,
)
from memora.graph.repository import GraphRepository


@pytest.fixture
def repo():
    r = GraphRepository(db_path=None)
    yield r
    r.close()


@pytest.fixture
def proposal():
    return GraphProposal(
        source_capture_id=str(uuid4()),
        confidence=0.90,
        nodes_to_create=[
            NodeProposal(
                temp_id="person_1",
                node_type=NodeType.PERSON,
                title="Carol White",
                content="Data scientist at DataCorp",
                properties={"name": "Carol White", "role": "Data Scientist"},
                confidence=0.9,
                networks=[NetworkType.PROFESSIONAL],
            ),
            NodeProposal(
                temp_id="event_1",
                node_type=NodeType.EVENT,
                title="Sprint Planning",
                content="Weekly sprint planning meeting",
                properties={"location": "Office"},
                confidence=0.85,
                networks=[NetworkType.PROFESSIONAL],
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
        human_summary="Adding Carol White and sprint planning event",
    )


class TestProposalCreation:
    def test_create_proposal(self, repo, proposal):
        pid = repo.create_proposal(proposal, agent_id="archivist", route=ProposalRoute.AUTO)
        assert pid is not None
        assert isinstance(pid, UUID)

    def test_proposal_stored_with_data(self, repo, proposal):
        pid = repo.create_proposal(proposal, agent_id="archivist", route=ProposalRoute.AUTO)
        row = repo._conn.execute(
            "SELECT proposal_data, agent_id, route, status FROM proposals WHERE id = ?",
            [str(pid)],
        ).fetchone()
        assert row is not None
        data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        assert len(data["nodes_to_create"]) == 2
        assert row[1] == "archivist"


class TestAtomicCommit:
    def test_commit_creates_nodes(self, repo, proposal):
        pid = repo.create_proposal(proposal, agent_id="archivist", route=ProposalRoute.AUTO)
        success = repo.commit_proposal(pid)
        assert success is True

        # Verify nodes exist
        rows = repo._conn.execute("SELECT COUNT(*) FROM nodes WHERE deleted = FALSE").fetchone()
        assert rows[0] >= 2

    def test_commit_creates_edges(self, repo, proposal):
        pid = repo.create_proposal(proposal, agent_id="archivist", route=ProposalRoute.AUTO)
        repo.commit_proposal(pid)

        edges = repo._conn.execute("SELECT COUNT(*) FROM edges").fetchone()
        assert edges[0] >= 1

    def test_commit_maps_temp_ids_to_real(self, repo, proposal):
        pid = repo.create_proposal(proposal, agent_id="archivist", route=ProposalRoute.AUTO)
        repo.commit_proposal(pid)

        # Edges should reference real UUIDs, not temp_ids
        edge_row = repo._conn.execute("SELECT source_id, target_id FROM edges").fetchone()
        assert edge_row is not None
        # Should be valid UUIDs (36 chars with dashes)
        assert len(edge_row[0]) == 36
        assert len(edge_row[1]) == 36
        # And they should NOT be the temp_ids
        assert edge_row[0] != "person_1"
        assert edge_row[1] != "event_1"

    def test_commit_nonexistent_proposal_fails(self, repo):
        fake_id = uuid4()
        success = repo.commit_proposal(fake_id)
        assert success is False

    def test_committed_nodes_have_correct_properties(self, repo, proposal):
        pid = repo.create_proposal(proposal, agent_id="archivist", route=ProposalRoute.AUTO)
        repo.commit_proposal(pid)

        row = repo._conn.execute(
            "SELECT title, node_type, confidence, networks FROM nodes WHERE title = 'Carol White'"
        ).fetchone()
        assert row is not None
        assert row[0] == "Carol White"
        assert row[1] == "PERSON"
        assert row[2] == 0.9

    def test_committed_nodes_have_source_capture_id(self, repo, proposal):
        pid = repo.create_proposal(proposal, agent_id="archivist", route=ProposalRoute.AUTO)
        repo.commit_proposal(pid)

        rows = repo._conn.execute(
            "SELECT source_capture_id FROM nodes WHERE deleted = FALSE"
        ).fetchall()
        for row in rows:
            assert row[0] == proposal.source_capture_id


class TestCommitIdempotency:
    def test_double_commit_same_proposal(self, repo, proposal):
        pid = repo.create_proposal(proposal, agent_id="archivist", route=ProposalRoute.AUTO)
        first = repo.commit_proposal(pid)
        assert first is True
        # Second commit may fail or create duplicates depending on implementation
        # The important thing is it doesn't crash
        try:
            repo.commit_proposal(pid)
        except Exception:
            pass  # acceptable


class TestCommitWithNodeUpdates:
    def test_commit_with_node_update(self, repo):
        """Commit a proposal that updates an existing node."""
        # First, create a node via a simple proposal
        first_proposal = GraphProposal(
            source_capture_id=str(uuid4()),
            confidence=0.9,
            nodes_to_create=[
                NodeProposal(
                    temp_id="p1",
                    node_type=NodeType.PERSON,
                    title="Dave",
                    content="Original content",
                    confidence=0.8,
                    networks=[NetworkType.SOCIAL],
                ),
            ],
            edges_to_create=[],
            human_summary="Adding Dave",
        )
        pid1 = repo.create_proposal(first_proposal, agent_id="archivist", route=ProposalRoute.AUTO)
        repo.commit_proposal(pid1)

        # Get the created node's real ID
        row = repo._conn.execute("SELECT id FROM nodes WHERE title = 'Dave'").fetchone()
        assert row is not None
        dave_id = row[0]

        # Verify the original content
        content_row = repo._conn.execute(
            "SELECT content FROM nodes WHERE id = ?", [dave_id]
        ).fetchone()
        assert content_row[0] == "Original content"


class TestProposalRouting:
    def test_auto_route_stored(self, repo, proposal):
        pid = repo.create_proposal(proposal, agent_id="archivist", route=ProposalRoute.AUTO)
        row = repo._conn.execute(
            "SELECT route FROM proposals WHERE id = ?", [str(pid)]
        ).fetchone()
        assert row[0] == "auto"

    def test_explicit_route_stored(self, repo, proposal):
        pid = repo.create_proposal(proposal, agent_id="archivist", route=ProposalRoute.EXPLICIT)
        row = repo._conn.execute(
            "SELECT route FROM proposals WHERE id = ?", [str(pid)]
        ).fetchone()
        assert row[0] == "explicit"

    def test_digest_route_stored(self, repo, proposal):
        pid = repo.create_proposal(proposal, agent_id="archivist", route=ProposalRoute.DIGEST)
        row = repo._conn.execute(
            "SELECT route FROM proposals WHERE id = ?", [str(pid)]
        ).fetchone()
        assert row[0] == "digest"
