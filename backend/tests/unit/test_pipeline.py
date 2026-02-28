"""Tests for the 9-stage extraction pipeline."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import pytest

from memora.core.pipeline import ExtractionPipeline, PipelineState, PipelineStage
from memora.graph.models import (
    Capture,
    EdgeCategory,
    EdgeProposal,
    EdgeType,
    GraphProposal,
    NetworkType,
    NodeProposal,
    NodeType,
    ProposalRoute,
)
from memora.core.entity_resolution import ResolutionOutcome, ResolutionResult
from memora.graph.repository import GraphRepository


@pytest.fixture
def repo():
    r = GraphRepository(db_path=None)
    yield r
    r.close()


@pytest.fixture
def pipeline(repo):
    return ExtractionPipeline(repo=repo)


@pytest.fixture
def sample_proposal():
    return GraphProposal(
        source_capture_id=str(uuid4()),
        confidence=0.90,
        nodes_to_create=[
            NodeProposal(
                temp_id="person_1",
                node_type=NodeType.PERSON,
                title="Alice Smith",
                content="Colleague at Acme Corp",
                properties={"name": "Alice Smith", "role": "Engineer"},
                confidence=0.9,
                networks=[NetworkType.PROFESSIONAL],
            ),
        ],
        edges_to_create=[],
        human_summary="Adding Alice Smith",
    )


# ── Stage 2: Preprocessing ──────────────────────────────────────────


class TestPreprocessing:
    @pytest.mark.asyncio
    async def test_text_normalization_strips_whitespace(self, pipeline):
        state = PipelineState(capture_id=str(uuid4()), raw_content="  Hello world  ")
        result = await pipeline._preprocess(state)
        assert result.processed_content == "Hello world"
        assert result.content_hash != ""

    @pytest.mark.asyncio
    async def test_date_normalization_today(self, pipeline):
        today = datetime.utcnow().date().isoformat()
        state = PipelineState(capture_id=str(uuid4()), raw_content="I have a meeting today")
        result = await pipeline._preprocess(state)
        assert today in result.processed_content

    @pytest.mark.asyncio
    async def test_date_normalization_tomorrow(self, pipeline):
        tomorrow = (datetime.utcnow().date() + timedelta(days=1)).isoformat()
        state = PipelineState(capture_id=str(uuid4()), raw_content="Deadline is tomorrow")
        result = await pipeline._preprocess(state)
        assert tomorrow in result.processed_content

    @pytest.mark.asyncio
    async def test_currency_normalization_k(self, pipeline):
        state = PipelineState(capture_id=str(uuid4()), raw_content="Salary is $50k per year")
        result = await pipeline._preprocess(state)
        assert "$50,000.00" in result.processed_content

    @pytest.mark.asyncio
    async def test_currency_normalization_bucks(self, pipeline):
        state = PipelineState(capture_id=str(uuid4()), raw_content="Spent 20 bucks on lunch")
        result = await pipeline._preprocess(state)
        assert "$20.00" in result.processed_content

    @pytest.mark.asyncio
    async def test_duplicate_detection(self, pipeline, repo):
        content = "Unique content for dedup test"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        # Insert a capture with the same hash
        repo._conn.execute(
            "INSERT INTO captures (id, modality, raw_content, content_hash) VALUES (?, ?, ?, ?)",
            [str(uuid4()), "text", content, content_hash],
        )
        state = PipelineState(capture_id=str(uuid4()), raw_content=content)
        result = await pipeline._preprocess(state)
        assert result.is_duplicate is True
        assert result.error == "Duplicate content detected"

    @pytest.mark.asyncio
    async def test_language_detection_english(self, pipeline):
        state = PipelineState(
            capture_id=str(uuid4()),
            raw_content="This is a normal English sentence about meetings.",
        )
        result = await pipeline._preprocess(state)
        assert result.language == "en"


# ── Stage 3: Extraction ─────────────────────────────────────────────


class TestExtraction:
    @pytest.mark.asyncio
    async def test_no_archivist_fails(self, pipeline):
        state = PipelineState(
            capture_id=str(uuid4()),
            raw_content="test",
            processed_content="test",
        )
        result = await pipeline._extract(state)
        assert result.error is not None
        assert "Archivist" in result.error

    @pytest.mark.asyncio
    async def test_extraction_with_mock_archivist(self, repo, sample_proposal):
        from memora.agents.archivist import ArchivistResult

        mock_archivist = MagicMock()
        mock_archivist.extract.return_value = ArchivistResult(
            proposal=sample_proposal,
            clarification_needed=False,
            raw_response="{}",
            token_usage={"input_tokens": 100, "output_tokens": 50},
        )

        pipeline = ExtractionPipeline(repo=repo, archivist=mock_archivist)
        state = PipelineState(
            capture_id=str(uuid4()),
            raw_content="met Alice",
            processed_content="met Alice",
        )
        result = await pipeline._extract(state)
        assert result.proposal is not None
        assert result.proposal.confidence == 0.90

    @pytest.mark.asyncio
    async def test_extraction_clarification_needed(self, repo):
        from memora.agents.archivist import ArchivistResult

        mock_archivist = MagicMock()
        mock_archivist.extract.return_value = ArchivistResult(
            proposal=None,
            clarification_needed=True,
            clarification_message="What did you mean by 'the thing'?",
        )

        pipeline = ExtractionPipeline(repo=repo, archivist=mock_archivist)
        state = PipelineState(
            capture_id=str(uuid4()),
            raw_content="do the thing",
            processed_content="do the thing",
        )
        result = await pipeline._extract(state)
        assert result.clarification_needed is True
        assert "the thing" in result.clarification_message


# ── Stage 4: Entity Resolution ──────────────────────────────────────


class TestEntityResolutionStage:
    @pytest.mark.asyncio
    async def test_empty_proposal_skips(self, pipeline):
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal = None
        result = await pipeline._resolve_entities(state)
        assert result.resolutions is None

    @pytest.mark.asyncio
    async def test_resolution_runs_for_nodes(self, repo, sample_proposal):
        mock_resolver = MagicMock()
        mock_resolver.resolve_nodes.return_value = [
            ResolutionResult(
                proposed_temp_id="person_1",
                proposed_title="Alice Smith",
                outcome=ResolutionOutcome.CREATE,
            )
        ]

        pipeline = ExtractionPipeline(repo=repo, resolver=mock_resolver)
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal = sample_proposal
        result = await pipeline._resolve_entities(state)
        assert len(result.resolutions) == 1
        assert result.resolutions[0].outcome == ResolutionOutcome.CREATE


# ── Stage 5: Proposal Assembly ──────────────────────────────────────


class TestProposalAssembly:
    @pytest.mark.asyncio
    async def test_no_resolutions_skips(self, pipeline, sample_proposal):
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal = sample_proposal
        state.resolutions = None
        result = await pipeline._assemble_proposal(state)
        assert result.proposal is sample_proposal  # unchanged

    @pytest.mark.asyncio
    async def test_apply_merges(self, repo, sample_proposal):
        mock_resolver = MagicMock()
        mock_resolver.apply_merges.return_value = sample_proposal

        pipeline = ExtractionPipeline(repo=repo, resolver=mock_resolver)
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal = sample_proposal
        state.resolutions = [
            ResolutionResult(
                proposed_temp_id="person_1",
                proposed_title="Alice Smith",
                outcome=ResolutionOutcome.CREATE,
            )
        ]
        result = await pipeline._assemble_proposal(state)
        mock_resolver.apply_merges.assert_called_once()


# ── Stage 6: Validation Gate ────────────────────────────────────────


class TestValidationGate:
    @pytest.mark.asyncio
    async def test_high_confidence_auto_approves(self, pipeline, sample_proposal):
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal = sample_proposal  # confidence=0.90
        state.resolutions = []
        result = await pipeline._validation_gate(state)
        assert result.route == ProposalRoute.AUTO

    @pytest.mark.asyncio
    async def test_low_confidence_goes_to_digest(self, pipeline):
        low_conf_proposal = GraphProposal(
            source_capture_id=str(uuid4()),
            confidence=0.50,
            nodes_to_create=[],
            edges_to_create=[],
            human_summary="low confidence test",
        )
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal = low_conf_proposal
        state.resolutions = []
        result = await pipeline._validation_gate(state)
        assert result.route == ProposalRoute.DIGEST

    @pytest.mark.asyncio
    async def test_merges_require_explicit_review(self, pipeline, sample_proposal):
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal = sample_proposal
        state.resolutions = [
            ResolutionResult(
                proposed_temp_id="person_1",
                proposed_title="Alice Smith",
                outcome=ResolutionOutcome.MERGE,
            )
        ]
        result = await pipeline._validation_gate(state)
        assert result.route == ProposalRoute.EXPLICIT

    @pytest.mark.asyncio
    async def test_deferred_requires_explicit_review(self, pipeline, sample_proposal):
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal = sample_proposal
        state.resolutions = [
            ResolutionResult(
                proposed_temp_id="person_1",
                proposed_title="Alice Smith",
                outcome=ResolutionOutcome.DEFER,
            )
        ]
        result = await pipeline._validation_gate(state)
        assert result.route == ProposalRoute.EXPLICIT


# ── Stage 7: Review ─────────────────────────────────────────────────


class TestReview:
    @pytest.mark.asyncio
    async def test_auto_route_continues(self, pipeline, sample_proposal):
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal = sample_proposal
        state.route = ProposalRoute.AUTO
        result = await pipeline._review(state)
        assert result.proposal_id is not None
        assert result.status == "processing"  # not "awaiting_review"

    @pytest.mark.asyncio
    async def test_explicit_route_awaits_review(self, pipeline, sample_proposal):
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal = sample_proposal
        state.route = ProposalRoute.EXPLICIT
        result = await pipeline._review(state)
        assert result.proposal_id is not None
        assert result.status == "awaiting_review"


# ── Stage 8: Graph Commit ───────────────────────────────────────────


class TestGraphCommit:
    @pytest.mark.asyncio
    async def test_auto_route_commits(self, pipeline, sample_proposal):
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal = sample_proposal
        state.route = ProposalRoute.AUTO
        # First review to get proposal_id
        state = await pipeline._review(state)
        # Then commit
        result = await pipeline._commit(state)
        assert result.error is None

    @pytest.mark.asyncio
    async def test_non_auto_skips_commit(self, pipeline, sample_proposal):
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal = sample_proposal
        state.route = ProposalRoute.EXPLICIT
        state = await pipeline._review(state)
        result = await pipeline._commit(state)
        # Should skip commit, no error
        assert result.error is None

    @pytest.mark.asyncio
    async def test_no_proposal_id_skips(self, pipeline):
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.route = ProposalRoute.AUTO
        result = await pipeline._commit(state)
        assert result.error is None


# ── Stage 9: Post-Commit ────────────────────────────────────────────


class TestPostCommit:
    @pytest.mark.asyncio
    async def test_skips_on_error(self, pipeline):
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.error = "previous error"
        state.proposal_id = str(uuid4())
        result = await pipeline._post_commit(state)
        # Should return without doing anything
        assert result.error == "previous error"

    @pytest.mark.asyncio
    async def test_skips_non_auto(self, pipeline, sample_proposal):
        state = PipelineState(capture_id=str(uuid4()), raw_content="test")
        state.proposal_id = str(uuid4())
        state.route = ProposalRoute.EXPLICIT
        result = await pipeline._post_commit(state)
        assert result.error is None


# ── Full pipeline run ────────────────────────────────────────────────


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_without_archivist_fails_at_extraction(self, pipeline):
        state = await pipeline.run(str(uuid4()), "Test input text")
        assert state.status == "failed"
        assert state.stage == PipelineStage.EXTRACTION

    @pytest.mark.asyncio
    async def test_pipeline_end_to_end_with_mock(self, repo, sample_proposal):
        from memora.agents.archivist import ArchivistResult

        mock_archivist = MagicMock()
        mock_archivist.extract.return_value = ArchivistResult(
            proposal=sample_proposal,
            clarification_needed=False,
            raw_response="{}",
            token_usage={"input_tokens": 100, "output_tokens": 50},
        )

        mock_resolver = MagicMock()
        mock_resolver.resolve_nodes.return_value = [
            ResolutionResult(
                proposed_temp_id="person_1",
                proposed_title="Alice Smith",
                outcome=ResolutionOutcome.CREATE,
            )
        ]
        mock_resolver.apply_merges.return_value = sample_proposal

        pipeline = ExtractionPipeline(
            repo=repo,
            archivist=mock_archivist,
            resolver=mock_resolver,
        )

        state = await pipeline.run(str(uuid4()), "Met Alice Smith at Acme Corp")
        assert state.status == "completed"
        assert state.proposal_id is not None

    @pytest.mark.asyncio
    async def test_pipeline_duplicate_stops_early(self, repo):
        content = "Exact duplicate content for pipeline test"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        repo._conn.execute(
            "INSERT INTO captures (id, modality, raw_content, content_hash) VALUES (?, ?, ?, ?)",
            [str(uuid4()), "text", content, content_hash],
        )

        pipeline = ExtractionPipeline(repo=repo)
        state = await pipeline.run(str(uuid4()), content)
        assert state.status == "failed"
        assert state.stage == PipelineStage.PREPROCESSING
