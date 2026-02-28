"""Tests for the multi-signal entity resolution engine."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from memora.core.entity_resolution import (
    EntityResolver,
    ResolutionCandidate,
    ResolutionOutcome,
    ResolutionResult,
)
from memora.graph.models import (
    EdgeCategory,
    EdgeProposal,
    EdgeType,
    GraphProposal,
    NetworkType,
    NodeProposal,
    NodeType,
)
from memora.graph.repository import GraphRepository


@pytest.fixture
def repo():
    r = GraphRepository(db_path=None)
    yield r
    r.close()


@pytest.fixture
def resolver(repo):
    return EntityResolver(repo=repo)


@pytest.fixture
def sample_proposal():
    return GraphProposal(
        source_capture_id=str(uuid4()),
        confidence=0.90,
        nodes_to_create=[
            NodeProposal(
                temp_id="person_1",
                node_type=NodeType.PERSON,
                title="Bob Johnson",
                content="Project manager at TechCorp",
                properties={"name": "Bob Johnson"},
                confidence=0.9,
                networks=[NetworkType.PROFESSIONAL],
            ),
        ],
        edges_to_create=[],
        human_summary="Adding Bob Johnson",
    )


def _insert_node(repo, title, node_type="PERSON", networks=None):
    """Helper to insert a node directly into the DB."""
    import hashlib
    import json
    from datetime import datetime

    nid = str(uuid4())
    content_hash = hashlib.sha256(f"{title}|".encode()).hexdigest()
    now = datetime.utcnow().isoformat()
    repo._conn.execute(
        """INSERT INTO nodes (id, node_type, title, content, content_hash,
           properties, confidence, networks, human_approved, proposed_by,
           source_capture_id, access_count, decay_score, tags,
           created_at, updated_at, deleted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            nid, node_type, title, "", content_hash,
            json.dumps({}), 0.9, networks or [], False, "test",
            None, 0, 1.0, [], now, now, False,
        ],
    )
    return nid


# ── Signal: Exact Name Match ────────────────────────────────────────


class TestExactNameSignal:
    def test_exact_match_scores_1(self, resolver):
        candidate = ResolutionCandidate(
            existing_node_id=str(uuid4()),
            existing_title="Bob Johnson",
            existing_node_type="PERSON",
        )
        node = NodeProposal(
            temp_id="p1", node_type=NodeType.PERSON,
            title="Bob Johnson", content="", confidence=0.9,
            networks=[NetworkType.PROFESSIONAL],
        )
        resolver._score_exact_name(candidate, node)
        assert candidate.signals["exact_name"] == 1.0

    def test_case_insensitive_match(self, resolver):
        candidate = ResolutionCandidate(
            existing_node_id=str(uuid4()),
            existing_title="bob johnson",
            existing_node_type="PERSON",
        )
        node = NodeProposal(
            temp_id="p1", node_type=NodeType.PERSON,
            title="Bob Johnson", content="", confidence=0.9,
            networks=[NetworkType.PROFESSIONAL],
        )
        resolver._score_exact_name(candidate, node)
        assert candidate.signals["exact_name"] == 1.0

    def test_no_match_scores_0(self, resolver):
        candidate = ResolutionCandidate(
            existing_node_id=str(uuid4()),
            existing_title="Alice Smith",
            existing_node_type="PERSON",
        )
        node = NodeProposal(
            temp_id="p1", node_type=NodeType.PERSON,
            title="Bob Johnson", content="", confidence=0.9,
            networks=[NetworkType.PROFESSIONAL],
        )
        resolver._score_exact_name(candidate, node)
        assert candidate.signals["exact_name"] == 0.0


# ── Signal: Network Overlap ─────────────────────────────────────────


class TestNetworkOverlapSignal:
    def test_full_overlap(self, resolver):
        candidate = ResolutionCandidate(
            existing_node_id=str(uuid4()),
            existing_title="X",
            existing_node_type="PERSON",
            existing_networks=["PROFESSIONAL"],
        )
        node = NodeProposal(
            temp_id="p1", node_type=NodeType.PERSON,
            title="X", content="", confidence=0.9,
            networks=[NetworkType.PROFESSIONAL],
        )
        resolver._score_network_overlap(candidate, node)
        assert candidate.signals["same_network"] == 1.0

    def test_partial_overlap(self, resolver):
        candidate = ResolutionCandidate(
            existing_node_id=str(uuid4()),
            existing_title="X",
            existing_node_type="PERSON",
            existing_networks=["PROFESSIONAL", "SOCIAL"],
        )
        node = NodeProposal(
            temp_id="p1", node_type=NodeType.PERSON,
            title="X", content="", confidence=0.9,
            networks=[NetworkType.PROFESSIONAL],
        )
        resolver._score_network_overlap(candidate, node)
        assert candidate.signals["same_network"] == 0.5

    def test_no_overlap(self, resolver):
        candidate = ResolutionCandidate(
            existing_node_id=str(uuid4()),
            existing_title="X",
            existing_node_type="PERSON",
            existing_networks=["HEALTH"],
        )
        node = NodeProposal(
            temp_id="p1", node_type=NodeType.PERSON,
            title="X", content="", confidence=0.9,
            networks=[NetworkType.PROFESSIONAL],
        )
        resolver._score_network_overlap(candidate, node)
        assert candidate.signals["same_network"] == 0.0

    def test_empty_networks(self, resolver):
        candidate = ResolutionCandidate(
            existing_node_id=str(uuid4()),
            existing_title="X",
            existing_node_type="PERSON",
            existing_networks=[],
        )
        node = NodeProposal(
            temp_id="p1", node_type=NodeType.PERSON,
            title="X", content="", confidence=0.9,
            networks=[],
        )
        resolver._score_network_overlap(candidate, node)
        assert candidate.signals["same_network"] == 0.0


# ── Signal: Embedding Similarity ────────────────────────────────────


class TestEmbeddingSignal:
    def test_high_similarity_above_threshold(self, resolver):
        candidate = ResolutionCandidate(
            existing_node_id="node-123",
            existing_title="X",
            existing_node_type="PERSON",
        )
        similar_nodes = [
            {"node_id": "node-123", "score": 0.95, "content": "X"},
        ]
        resolver._score_embedding(candidate, similar_nodes)
        assert candidate.signals["embedding_similarity"] == 0.95

    def test_low_similarity_below_threshold(self, resolver):
        candidate = ResolutionCandidate(
            existing_node_id="node-123",
            existing_title="X",
            existing_node_type="PERSON",
        )
        similar_nodes = [
            {"node_id": "node-123", "score": 0.80, "content": "X"},
        ]
        resolver._score_embedding(candidate, similar_nodes)
        # Below EMBEDDING_THRESHOLD (0.92), so score * 0.5
        assert candidate.signals["embedding_similarity"] == 0.40

    def test_no_similar_node(self, resolver):
        candidate = ResolutionCandidate(
            existing_node_id="node-123",
            existing_title="X",
            existing_node_type="PERSON",
        )
        resolver._score_embedding(candidate, [])
        assert candidate.signals["embedding_similarity"] == 0.0


# ── Signal: Temporal Proximity ──────────────────────────────────────


class TestTemporalSignal:
    def test_same_day_scores_1(self, resolver, repo):
        nid = _insert_node(repo, "Test Node")
        candidate = ResolutionCandidate(
            existing_node_id=nid,
            existing_title="Test Node",
            existing_node_type="PERSON",
        )
        node = NodeProposal(
            temp_id="p1", node_type=NodeType.PERSON,
            title="Test Node", content="", confidence=0.9,
            networks=[NetworkType.PROFESSIONAL],
        )
        resolver._score_temporal(candidate, node)
        assert candidate.signals["temporal_proximity"] > 0.8


# ── Signal: Shared Relationships ────────────────────────────────────


class TestSharedRelationshipsSignal:
    def test_no_existing_edges(self, resolver, repo, sample_proposal):
        nid = _insert_node(repo, "Bob Johnson")
        candidate = ResolutionCandidate(
            existing_node_id=nid,
            existing_title="Bob Johnson",
            existing_node_type="PERSON",
        )
        node = sample_proposal.nodes_to_create[0]
        resolver._score_shared_relationships(candidate, node, sample_proposal)
        assert candidate.signals["shared_relationships"] == 0.0


# ── Weighted Sum ─────────────────────────────────────────────────────


class TestWeightedSum:
    def test_empty_signals(self, resolver):
        assert resolver._weighted_sum({}) == 0.0

    def test_single_signal(self, resolver):
        score = resolver._weighted_sum({"exact_name": 1.0})
        assert score == 1.0  # 1.0 * 0.95 / 0.95

    def test_multiple_signals(self, resolver):
        signals = {"exact_name": 1.0, "same_network": 1.0}
        score = resolver._weighted_sum(signals)
        expected = (1.0 * 0.95 + 1.0 * 0.15) / (0.95 + 0.15)
        assert abs(score - expected) < 0.001


# ── Outcome Determination ───────────────────────────────────────────


class TestOutcomeDetermination:
    def test_no_candidates_creates_new(self, resolver, sample_proposal):
        results = resolver.resolve_nodes(sample_proposal)
        assert len(results) == 1
        assert results[0].outcome == ResolutionOutcome.CREATE

    def test_exact_match_finds_candidate(self, resolver, repo, sample_proposal):
        _insert_node(repo, "Bob Johnson", "PERSON", ["PROFESSIONAL"])
        results = resolver.resolve_nodes(sample_proposal)
        assert len(results) == 1
        # Without embedding similarity, exact name alone is diluted
        # by other 0-scoring signals below MERGE threshold.
        # But a candidate should still be found.
        assert len(results[0].candidates) >= 1
        assert results[0].candidates[0].signals.get("exact_name") == 1.0

    def test_different_type_no_match(self, resolver, repo, sample_proposal):
        _insert_node(repo, "Bob Johnson", "EVENT")
        results = resolver.resolve_nodes(sample_proposal)
        assert len(results) == 1
        assert results[0].outcome == ResolutionOutcome.CREATE


# ── Apply Merges ─────────────────────────────────────────────────────


class TestApplyMerges:
    def test_no_merges_returns_unchanged(self, resolver, sample_proposal):
        resolutions = [
            ResolutionResult(
                proposed_temp_id="person_1",
                proposed_title="Bob Johnson",
                outcome=ResolutionOutcome.CREATE,
            )
        ]
        result = resolver.apply_merges(sample_proposal, resolutions)
        assert len(result.nodes_to_create) == 1

    def test_merge_removes_node_adds_update(self, resolver, sample_proposal):
        existing_id = str(uuid4())
        candidate = ResolutionCandidate(
            existing_node_id=existing_id,
            existing_title="Bob Johnson",
            existing_node_type="PERSON",
        )
        resolutions = [
            ResolutionResult(
                proposed_temp_id="person_1",
                proposed_title="Bob Johnson",
                outcome=ResolutionOutcome.MERGE,
                chosen=candidate,
            )
        ]
        result = resolver.apply_merges(sample_proposal, resolutions)
        assert len(result.nodes_to_create) == 0
        assert len(result.nodes_to_update) >= 1
        assert result.nodes_to_update[0].node_id == existing_id

    def test_merge_rewrites_edge_references(self, resolver):
        existing_id = str(uuid4())
        proposal = GraphProposal(
            source_capture_id=str(uuid4()),
            confidence=0.90,
            nodes_to_create=[
                NodeProposal(
                    temp_id="person_1",
                    node_type=NodeType.PERSON,
                    title="Bob",
                    content="",
                    confidence=0.9,
                    networks=[NetworkType.PROFESSIONAL],
                ),
                NodeProposal(
                    temp_id="event_1",
                    node_type=NodeType.EVENT,
                    title="Meeting",
                    content="",
                    confidence=0.9,
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
            human_summary="test",
        )

        candidate = ResolutionCandidate(
            existing_node_id=existing_id,
            existing_title="Bob",
            existing_node_type="PERSON",
        )
        resolutions = [
            ResolutionResult(
                proposed_temp_id="person_1",
                proposed_title="Bob",
                outcome=ResolutionOutcome.MERGE,
                chosen=candidate,
            ),
            ResolutionResult(
                proposed_temp_id="event_1",
                proposed_title="Meeting",
                outcome=ResolutionOutcome.CREATE,
            ),
        ]
        result = resolver.apply_merges(proposal, resolutions)
        # Edge source_id should be rewritten to existing_id
        assert result.edges_to_create[0].source_id == existing_id
        # Edge target_id should stay as temp_id (event_1 is CREATE)
        assert result.edges_to_create[0].target_id == "event_1"
