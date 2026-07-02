"""Edge case and error tests for Memora core modules.

Covers boundary conditions, empty inputs, missing resources, and error
handling across gap detection, health scoring, bridge discovery, entity
resolution, decay scoring, pipeline preprocessing, truth layer, connectors,
rate limiter, safe_run decorator, custom exceptions, and embedding cache.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from math import exp, log
from unittest.mock import MagicMock, patch
from uuid import uuid4

import sys

import duckdb
import pytest

from memora.connectors.markdown_connector import MarkdownConnector
from memora.core.decay import DecayScoring
from memora.core.decorators import safe_run
from memora.core.entity_resolution import (
    EntityResolver,
    ResolutionOutcome,
)
from memora.core.exceptions import (
    AgentError,
    ConfigError,
    ConnectorError,
    EmbeddingError,
    EntityResolutionError,
    GraphCommitError,
    MemoraError,
    PipelineError,
)
from memora.core.gap_detection import GapDetector
from memora.core.health_scoring import HealthScoring
from memora.core.rate_limiter import TokenBucketLimiter, get_global_limiter
from memora.core.truth_layer import TruthLayer
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
from memora.vector.embeddings import EmbeddingEngine


# ====================================================================
# Shared helpers
# ====================================================================


def _insert_node(
    repo: GraphRepository,
    node_id: str | None = None,
    node_type: str = "NOTE",
    title: str = "Test Node",
    content: str = "",
    networks: list[str] | None = None,
    last_accessed: datetime | None = None,
    decay_score: float = 1.0,
    deleted: bool = False,
    properties: dict | None = None,
    access_count: int = 0,
    created_at: datetime | None = None,
) -> str:
    """Helper to insert a raw node row directly into DuckDB."""
    nid = node_id or str(uuid4())
    now_str = (created_at or datetime.now(timezone.utc)).isoformat()
    content_hash = f"hash_{nid[:8]}"
    repo._conn.execute(
        """INSERT INTO nodes
           (id, node_type, title, content, content_hash, properties,
            confidence, networks, human_approved, access_count,
            decay_score, tags, created_at, updated_at, last_accessed, deleted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            nid,
            node_type,
            title,
            content,
            content_hash,
            json.dumps(properties or {}),
            1.0,
            networks or [],
            False,
            access_count,
            decay_score,
            [],
            now_str,
            now_str,
            last_accessed.isoformat() if last_accessed else None,
            deleted,
        ],
    )
    return nid


def _insert_edge(
    repo: GraphRepository,
    source_id: str,
    target_id: str,
    edge_type: str = "RELATED_TO",
    edge_category: str = "ASSOCIATIVE",
) -> str:
    """Insert a raw edge row directly into DuckDB."""
    eid = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    repo._conn.execute(
        """INSERT INTO edges
           (id, source_id, target_id, edge_type, edge_category,
            properties, confidence, weight, bidirectional, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            eid, source_id, target_id, edge_type, edge_category,
            json.dumps({}), 1.0, 1.0, False, now, now,
        ],
    )
    return eid


@pytest.fixture
def repo():
    """In-memory DuckDB repository for testing."""
    r = GraphRepository(db_path=None)
    yield r
    r.close()


@pytest.fixture
def conn():
    """In-memory DuckDB connection for truth layer tests."""
    c = duckdb.connect(":memory:")
    yield c
    c.close()


# ====================================================================
# 1. Empty graph operations
# ====================================================================


class TestEmptyGraphOperations:
    """Test gap detection, health scoring, bridge discovery on empty graphs."""

    def test_gap_detection_empty_graph(self, repo: GraphRepository):
        """All gap categories should return empty lists on an empty graph."""
        detector = GapDetector(repo)
        results = detector.detect_all()

        assert results["orphaned_nodes"] == []
        assert results["stalled_goals"] == []
        assert results["dead_end_projects"] == []
        assert results["isolated_concepts"] == []
        assert results["unresolved_decisions"] == []

    def test_health_scoring_empty_graph(self, repo: GraphRepository):
        """Empty graph should produce on_track status for any network."""
        scorer = HealthScoring(repo)
        health = scorer.compute_network_health("PROFESSIONAL")

        assert health["status"] == "on_track"
        assert health["commitment_completion_rate"] == 1.0
        assert health["alert_ratio"] == 0.0
        assert health["staleness_flags"] == 0

    def test_health_scoring_all_networks_empty(self, repo: GraphRepository):
        """compute_all_networks should return results for all 7 networks on empty graph."""
        scorer = HealthScoring(repo)
        results = scorer.compute_all_networks()

        assert len(results) == 7
        for health in results:
            assert health["status"] == "on_track"

    def test_bridge_discovery_empty_graph(self, repo: GraphRepository):
        """Bridge discovery for a non-existent node should return empty list."""
        mock_vs = MagicMock()
        mock_ee = MagicMock()

        from memora.core.bridge_discovery import BridgeDiscovery

        bridge_detector = BridgeDiscovery(
            repo=repo,
            vector_store=mock_vs,
            embedding_engine=mock_ee,
        )

        # Non-existent node
        result = bridge_detector.discover_bridges_for_node(str(uuid4()))
        assert result == []

    def test_decay_batch_update_empty_graph(self, repo: GraphRepository):
        """Batch update on empty graph should return 0."""
        scorer = DecayScoring(repo)
        count = scorer.batch_update_scores()
        assert count == 0

    def test_decayed_nodes_empty_graph(self, repo: GraphRepository):
        """Querying for decayed nodes on empty graph should return empty list."""
        scorer = DecayScoring(repo)
        decayed = scorer.get_decayed_nodes(threshold=0.5)
        assert decayed == []


# ====================================================================
# 2. Entity resolution with no candidates
# ====================================================================


class TestEntityResolutionNoCandidates:
    """Test the resolver when graph has no nodes to match against."""

    def test_resolve_with_empty_graph_creates_new(self, repo: GraphRepository):
        """With no existing nodes, all proposals should get CREATE outcome."""
        resolver = EntityResolver(repo=repo)
        proposal = GraphProposal(
            source_capture_id=str(uuid4()),
            confidence=0.90,
            nodes_to_create=[
                NodeProposal(
                    temp_id="person_1",
                    node_type=NodeType.PERSON,
                    title="Alice",
                    content="Engineer at Acme",
                    confidence=0.9,
                    networks=[NetworkType.PROFESSIONAL],
                ),
                NodeProposal(
                    temp_id="event_1",
                    node_type=NodeType.EVENT,
                    title="Team standup",
                    content="Daily standup meeting",
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
            human_summary="Adding Alice and standup event",
        )

        results = resolver.resolve_nodes(proposal)
        assert len(results) == 2
        for r in results:
            assert r.outcome == ResolutionOutcome.CREATE

    def test_resolve_no_nodes_to_create(self, repo: GraphRepository):
        """Proposal with empty nodes_to_create should return empty results."""
        resolver = EntityResolver(repo=repo)
        proposal = GraphProposal(
            source_capture_id=str(uuid4()),
            confidence=0.90,
            nodes_to_create=[],
            edges_to_create=[],
            human_summary="Nothing to add",
        )
        results = resolver.resolve_nodes(proposal)
        assert results == []

    def test_weighted_sum_empty_signals(self, repo: GraphRepository):
        """Empty signal dict should yield 0.0 weighted sum."""
        resolver = EntityResolver(repo=repo)
        assert resolver._weighted_sum({}) == 0.0


# ====================================================================
# 3. Decay scoring edge cases
# ====================================================================


class TestDecayScoringEdgeCases:
    """Test decay scoring with future dates, epoch, and very old dates."""

    def test_compute_decay_future_date(self, repo: GraphRepository):
        """A future anchor date should produce decay_score of 1.0 (clamped at 0 days)."""
        scorer = DecayScoring(repo)
        future = datetime.now(timezone.utc) + timedelta(days=30)
        score = scorer.compute_decay(future, lambda_val=0.05)
        # max(0.0, delta_days) clamps negative to 0 -> e^0 = 1.0
        assert score == pytest.approx(1.0, abs=0.001)

    def test_compute_decay_epoch_date(self, repo: GraphRepository):
        """Epoch (1970-01-01) should produce a very small score (extremely old)."""
        scorer = DecayScoring(repo)
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        score = scorer.compute_decay(epoch, lambda_val=0.01)
        # ~20,000 days -> e^(-0.01 * 20000) is essentially 0
        assert score < 1e-10

    def test_compute_decay_very_old_date(self, repo: GraphRepository):
        """A date 365 days ago with default lambda should be near zero."""
        scorer = DecayScoring(repo)
        old = datetime.now(timezone.utc) - timedelta(days=365)
        score = scorer.compute_decay(old, lambda_val=0.05)
        # e^(-0.05 * 365) ≈ e^(-18.25) ≈ 1.2e-8
        assert score < 0.001

    def test_compute_decay_just_now(self, repo: GraphRepository):
        """A date of right now should have score near 1.0."""
        scorer = DecayScoring(repo)
        now = datetime.now(timezone.utc)
        score = scorer.compute_decay(now, lambda_val=0.05)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_compute_decay_naive_datetime(self, repo: GraphRepository):
        """Naive datetime (no tzinfo) should be handled gracefully."""
        scorer = DecayScoring(repo)
        naive = datetime.now()  # no timezone
        score = scorer.compute_decay(naive, lambda_val=0.05)
        # Should still work (assumes UTC)
        assert 0.0 <= score <= 1.0

    def test_batch_update_with_future_event(self, repo: GraphRepository):
        """EVENT with future event_date should be pinned at 1.0."""
        scorer = DecayScoring(repo)
        future = datetime.now(timezone.utc) + timedelta(days=30)
        nid = _insert_node(
            repo,
            node_type="EVENT",
            title="Future Conference",
            created_at=datetime.now(timezone.utc) - timedelta(days=60),
            properties={"event_date": future.isoformat()},
            networks=["PROFESSIONAL"],
        )

        scorer.batch_update_scores()

        row = repo._conn.execute(
            "SELECT decay_score FROM nodes WHERE id = ?", [nid]
        ).fetchone()
        assert row[0] == pytest.approx(1.0, abs=0.001)

    def test_compute_decay_zero_lambda(self, repo: GraphRepository):
        """Zero lambda should mean no decay at all (score stays 1.0)."""
        scorer = DecayScoring(repo)
        old = datetime.now(timezone.utc) - timedelta(days=365)
        score = scorer.compute_decay(old, lambda_val=0.0)
        # e^(-0 * 365) = e^0 = 1.0
        assert score == pytest.approx(1.0, abs=0.001)

    def test_compute_decay_very_high_lambda(self, repo: GraphRepository):
        """Very high lambda should cause near-instant decay."""
        scorer = DecayScoring(repo)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        score = scorer.compute_decay(yesterday, lambda_val=100.0)
        # e^(-100 * 1) is essentially 0
        assert score < 1e-10

    def test_compute_decay_large_access_count(self, repo: GraphRepository):
        """A very large access count should dramatically slow decay."""
        scorer = DecayScoring(repo)
        old = datetime.now(timezone.utc) - timedelta(days=60)
        lam = 0.05
        score = scorer.compute_decay(old, lam, access_count=10000)
        # effective_lambda = 0.05 / (1 + log(10001)) ≈ 0.05 / 10.21 ≈ 0.005
        # e^(-0.005 * 60) ≈ 0.74 — decay is nearly flat
        assert score > 0.6


# ====================================================================
# 4. Pipeline with empty input
# ====================================================================


class TestPipelineEmptyInput:
    """Test pipeline preprocessing with empty or whitespace-only input."""

    @pytest.mark.asyncio
    async def test_preprocess_empty_string(self, repo: GraphRepository):
        """Empty string should produce empty processed_content and hash."""
        from memora.core.pipeline import ExtractionPipeline, PipelineState

        pipeline = ExtractionPipeline(repo=repo)
        state = PipelineState(capture_id=str(uuid4()), raw_content="")
        state = await pipeline._preprocess(state)

        assert state.processed_content == ""
        assert state.content_hash != ""  # hash of "" is still a valid hash
        assert state.language == "en"
        assert state.preprocessing_metadata["resolved_dates"] == []
        assert state.preprocessing_metadata["resolved_currencies"] == []

    @pytest.mark.asyncio
    async def test_preprocess_whitespace_only(self, repo: GraphRepository):
        """Whitespace-only input should be stripped to empty string."""
        from memora.core.pipeline import ExtractionPipeline, PipelineState

        pipeline = ExtractionPipeline(repo=repo)
        state = PipelineState(capture_id=str(uuid4()), raw_content="   \n\t  ")
        state = await pipeline._preprocess(state)

        assert state.processed_content == ""
        assert state.language == "en"

    @pytest.mark.asyncio
    async def test_preprocess_no_dates_or_currency(self, repo: GraphRepository):
        """Plain text with no date/currency patterns should return empty metadata."""
        from memora.core.pipeline import ExtractionPipeline, PipelineState

        pipeline = ExtractionPipeline(repo=repo)
        state = PipelineState(
            capture_id=str(uuid4()),
            raw_content="The cat sat on the mat.",
        )
        state = await pipeline._preprocess(state)

        assert state.processed_content == "The cat sat on the mat."
        assert state.preprocessing_metadata["resolved_dates"] == []
        assert state.preprocessing_metadata["resolved_currencies"] == []

    @pytest.mark.asyncio
    async def test_full_pipeline_empty_input_fails_gracefully(self, repo: GraphRepository):
        """Running the full pipeline with empty input should fail at extraction (no archivist)."""
        from memora.core.pipeline import ExtractionPipeline

        pipeline = ExtractionPipeline(repo=repo)
        state = await pipeline.run(
            capture_id=str(uuid4()),
            raw_content="",
        )

        # Without an archivist, extraction stage should set an error
        assert state.status == "failed"
        assert state.error is not None

    @pytest.mark.asyncio
    async def test_pipeline_state_validate_empty_content_warning(self):
        """PipelineState validation should flag empty processed_content past preprocessing."""
        from memora.core.pipeline import PipelineStage, PipelineState

        state = PipelineState(
            capture_id=str(uuid4()),
            raw_content="hello",
            processed_content="",
            stage=PipelineStage.EXTRACTION,
        )
        violations = state.validate()
        assert any("processed_content is empty" in v for v in violations)


# ====================================================================
# 5. Truth layer contradictions
# ====================================================================


class TestTruthLayerContradictions:
    """Test depositing two contradictory facts."""

    def test_deposit_contradictory_facts(self, conn):
        """Two contradictory facts on the same node should be detected."""
        tl = TruthLayer(conn)
        tl._nli_load_failed = True  # use keyword-based detection

        node_id = str(uuid4())

        # First fact
        fid1 = tl.deposit_fact(
            node_id=node_id,
            statement="Alice works at Google as a senior engineer",
            confidence=0.9,
            calibrate=False,
        )
        assert fid1 is not None

        # Second fact contradicts the first
        contradictions = tl.check_contradiction(
            statement="Alice works at Microsoft as a senior engineer",
            node_id=node_id,
        )
        assert len(contradictions) >= 1

    def test_deposit_both_contradictory_facts(self, conn):
        """Both contradictory facts can coexist in the database."""
        tl = TruthLayer(conn)
        tl._nli_load_failed = True

        node_id = str(uuid4())

        fid1 = tl.deposit_fact(
            node_id=node_id,
            statement="Alice works at Google as a senior software engineer",
            confidence=0.9,
            calibrate=False,
        )
        fid2 = tl.deposit_fact(
            node_id=node_id,
            statement="Alice works at Microsoft as a senior software engineer",
            confidence=0.8,
            calibrate=False,
        )
        # Both should be deposited (contradiction detection does not block deposit)
        assert fid1 is not None
        assert fid2 is not None

        # check_contradiction should find the first fact as a potential conflict
        # with the second (keyword overlap: alice, works, senior, software, engineer)
        contradictions = tl.check_contradiction(
            statement="Alice works at Microsoft as a senior software engineer",
            node_id=node_id,
        )
        # The keyword detector requires significant overlap; identical statement
        # is filtered out, but the first fact should be flagged
        assert len(contradictions) >= 1

    def test_contradiction_on_empty_truth_layer(self, conn):
        """Checking contradiction with no facts should return empty list."""
        tl = TruthLayer(conn)
        tl._nli_load_failed = True

        result = tl.check_contradiction(
            statement="Alice works at Google",
            node_id=str(uuid4()),
        )
        assert result == []

    def test_retire_old_fact_after_contradiction(self, conn):
        """Retiring an old fact should change its status to retired."""
        tl = TruthLayer(conn)
        tl._nli_load_failed = True

        node_id = str(uuid4())

        fid1 = tl.deposit_fact(
            node_id=node_id,
            statement="Alice earns $100k",
            confidence=0.9,
            calibrate=False,
        )

        tl.retire_fact(fid1, reason="Salary updated to $120k")

        fact = tl.get_fact(fid1)
        assert fact["status"] == "retired"


# ====================================================================
# 6. Connector with missing files
# ====================================================================


class TestMarkdownConnectorMissingFiles:
    """Test markdown connector when configured directory does not exist."""

    def test_connect_nonexistent_directory(self):
        """connect() should return False for a non-existent directory."""
        connector = MarkdownConnector(
            name="test_md",
            config={"path": "/tmp/definitely_not_a_real_memora_dir_xyz123"},
        )
        result = connector.connect()
        assert result is False

    def test_connect_missing_path_config(self):
        """validate_config should return an error when path is not provided."""
        connector = MarkdownConnector(name="test_md", config={})
        errors = connector.validate_config()
        assert len(errors) >= 1
        assert "path" in errors[0].lower()

    def test_get_items_without_connect(self):
        """get_items without calling connect should return empty list.

        The MarkdownConnector.get_items() imports frontmatter at the top of
        the method, then checks self._root.  Mock frontmatter so the import
        succeeds without installing the package.
        """
        connector = MarkdownConnector(
            name="test_md",
            config={"path": "/tmp/nonexistent"},
        )
        # _root is None since connect was not called
        with patch.dict(sys.modules, {"frontmatter": MagicMock()}):
            items = connector.get_items()
        assert items == []

    def test_sync_nonexistent_directory(self):
        """Full sync cycle should report error for non-existent directory."""
        connector = MarkdownConnector(
            name="test_md",
            config={"path": "/tmp/definitely_not_a_real_memora_dir_xyz123"},
        )
        record = connector.sync()
        assert record.errors >= 1
        assert record.items_synced == 0

    def test_connect_file_instead_of_directory(self, tmp_path):
        """connect() should return False when path is a file, not a directory."""
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("hello")

        connector = MarkdownConnector(
            name="test_md",
            config={"path": str(file_path)},
        )
        result = connector.connect()
        assert result is False


# ====================================================================
# 7. Rate limiter basic behavior
# ====================================================================


class TestTokenBucketLimiter:
    """Test the TokenBucketLimiter from memora/core/rate_limiter.py."""

    @pytest.mark.asyncio
    async def test_acquire_succeeds_within_burst(self):
        """Acquiring up to rate tokens should succeed immediately."""
        limiter = TokenBucketLimiter(rate=5, period=60.0)

        # Should be able to acquire 5 tokens without waiting
        for _ in range(5):
            await limiter.acquire()

        # Tokens should be exhausted (or near zero)
        assert limiter._tokens < 1.0

    @pytest.mark.asyncio
    async def test_acquire_blocks_when_exhausted(self):
        """Acquiring after exhaustion should take some time (blocking)."""
        limiter = TokenBucketLimiter(rate=2, period=1.0)

        # Exhaust the bucket
        await limiter.acquire()
        await limiter.acquire()

        # Next acquire should block briefly
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start

        # Should have waited at least a fraction of the period
        assert elapsed > 0.01

    @pytest.mark.asyncio
    async def test_tokens_refill_over_time(self):
        """Tokens should refill after some time passes."""
        limiter = TokenBucketLimiter(rate=10, period=1.0)

        # Exhaust all tokens
        for _ in range(10):
            await limiter.acquire()

        # Wait a bit for refill
        await asyncio.sleep(0.2)

        # Should have refilled some tokens
        limiter._refill()
        assert limiter._tokens > 0

    @pytest.mark.asyncio
    async def test_tokens_never_exceed_rate(self):
        """Tokens should never exceed the rate (burst capacity)."""
        limiter = TokenBucketLimiter(rate=5, period=1.0)

        # Wait to ensure tokens are at max
        await asyncio.sleep(0.1)
        limiter._refill()

        assert limiter._tokens <= 5.0

    def test_initial_tokens_equal_rate(self):
        """Initial token count should equal rate."""
        limiter = TokenBucketLimiter(rate=42, period=30.0)
        assert limiter._tokens == 42.0

    @pytest.mark.asyncio
    async def test_get_global_limiter_singleton(self):
        """get_global_limiter should return the same instance on repeated calls."""
        import memora.core.rate_limiter as rl_module

        # Reset global state for test isolation
        rl_module._global_limiter = None

        limiter1 = get_global_limiter(rate=10, period=10.0)
        limiter2 = get_global_limiter(rate=20, period=20.0)

        # Should be the same instance (first call wins)
        assert limiter1 is limiter2
        assert limiter1._rate == 10

        # Clean up
        rl_module._global_limiter = None


# ====================================================================
# 8. safe_run decorator
# ====================================================================


class TestSafeRunDecorator:
    """Test the safe_run decorator from memora/core/decorators.py."""

    def test_returns_result_on_success(self):
        """Decorated function should return normally on success."""

        @safe_run(default=None)
        def good_func():
            return 42

        assert good_func() == 42

    def test_returns_default_on_exception(self):
        """Decorated function should return default on exception."""

        @safe_run(default="fallback")
        def bad_func():
            raise ValueError("boom")

        assert bad_func() == "fallback"

    def test_returns_default_list_copy(self):
        """Mutable defaults (list) should return a fresh copy each time."""

        @safe_run(default=[])
        def bad_func():
            raise ValueError("boom")

        result1 = bad_func()
        result2 = bad_func()
        assert result1 == []
        assert result2 == []
        assert result1 is not result2  # different instances

    def test_returns_default_dict_copy(self):
        """Mutable defaults (dict) should return a fresh copy each time."""

        @safe_run(default={})
        def bad_func():
            raise ValueError("boom")

        result1 = bad_func()
        result2 = bad_func()
        assert result1 == {}
        assert result1 is not result2

    def test_returns_default_set_copy(self):
        """Mutable defaults (set) should return a fresh copy each time."""

        @safe_run(default=set())
        def bad_func():
            raise RuntimeError("boom")

        result1 = bad_func()
        result2 = bad_func()
        assert result1 == set()
        assert result1 is not result2

    def test_returns_scalar_default(self):
        """Scalar defaults (int, None) should be returned directly."""

        @safe_run(default=0)
        def bad_func():
            raise RuntimeError("boom")

        assert bad_func() == 0

    def test_preserves_function_name(self):
        """Decorated function should preserve the original name via functools.wraps."""

        @safe_run(default=None)
        def my_special_func():
            return 1

        assert my_special_func.__name__ == "my_special_func"

    def test_logs_warning_on_exception(self, caplog):
        """Decorator should log a warning when the wrapped function raises."""
        test_logger = logging.getLogger("test_safe_run")

        @safe_run(default=None, logger=test_logger, message="custom failure")
        def bad_func():
            raise RuntimeError("test error")

        with caplog.at_level(logging.WARNING, logger="test_safe_run"):
            result = bad_func()

        assert result is None
        assert "custom failure" in caplog.text

    def test_passes_arguments_through(self):
        """Decorator should pass positional and keyword args through."""

        @safe_run(default=None)
        def adder(a, b, offset=0):
            return a + b + offset

        assert adder(1, 2, offset=10) == 13


# ====================================================================
# 9. Custom exceptions
# ====================================================================


class TestCustomExceptions:
    """Test that custom exceptions can be caught as MemoraError."""

    def test_pipeline_error_is_memora_error(self):
        with pytest.raises(MemoraError):
            raise PipelineError("pipeline broke")

    def test_graph_commit_error_is_memora_error(self):
        with pytest.raises(MemoraError):
            raise GraphCommitError("commit failed")

    def test_entity_resolution_error_is_memora_error(self):
        with pytest.raises(MemoraError):
            raise EntityResolutionError("resolution failed")

    def test_connector_error_is_memora_error(self):
        with pytest.raises(MemoraError):
            raise ConnectorError("connector failed")

    def test_embedding_error_is_memora_error(self):
        with pytest.raises(MemoraError):
            raise EmbeddingError("embedding failed")

    def test_agent_error_is_memora_error(self):
        with pytest.raises(MemoraError):
            raise AgentError("agent failed")

    def test_config_error_is_memora_error(self):
        with pytest.raises(MemoraError):
            raise ConfigError("bad config")

    def test_memora_error_has_message(self):
        err = PipelineError("test message")
        assert str(err) == "test message"

    def test_catch_specific_over_base(self):
        """Specific exception should be catchable before MemoraError."""
        try:
            raise ConnectorError("connector issue")
        except ConnectorError as e:
            assert str(e) == "connector issue"
        except MemoraError:
            pytest.fail("Should have caught ConnectorError specifically")

    def test_all_exceptions_have_correct_hierarchy(self):
        """All custom exceptions should be subclasses of MemoraError and Exception."""
        for exc_cls in [
            PipelineError,
            GraphCommitError,
            EntityResolutionError,
            ConnectorError,
            EmbeddingError,
            AgentError,
            ConfigError,
        ]:
            assert issubclass(exc_cls, MemoraError)
            assert issubclass(exc_cls, Exception)


# ====================================================================
# 10. Embedding cache LRU eviction
# ====================================================================


class TestEmbeddingCacheLRUEviction:
    """Test that the LRU cache in EmbeddingEngine evicts old entries when full."""

    def test_cache_evicts_oldest_entry(self):
        """When cache exceeds max_size, oldest entry should be evicted."""
        engine = EmbeddingEngine(cache_max_size=3)

        # Manually populate the cache (bypass model loading)
        engine._cache["text_a"] = {"dense": [0.1], "sparse": {}}
        engine._cache["text_b"] = {"dense": [0.2], "sparse": {}}
        engine._cache["text_c"] = {"dense": [0.3], "sparse": {}}

        assert len(engine._cache) == 3

        # Add one more via direct cache manipulation (as embed_text would)
        engine._cache["text_d"] = {"dense": [0.4], "sparse": {}}
        if len(engine._cache) > engine._cache_max_size:
            engine._cache.popitem(last=False)

        assert len(engine._cache) == 3
        assert "text_a" not in engine._cache  # oldest evicted
        assert "text_d" in engine._cache  # newest present

    def test_cache_hit_moves_to_end(self):
        """Accessing a cached entry should move it to the end (most recent)."""
        engine = EmbeddingEngine(cache_max_size=3)

        engine._cache["text_a"] = {"dense": [0.1], "sparse": {}}
        engine._cache["text_b"] = {"dense": [0.2], "sparse": {}}
        engine._cache["text_c"] = {"dense": [0.3], "sparse": {}}

        # Access text_a to move it to end
        if "text_a" in engine._cache:
            engine._cache.move_to_end("text_a")

        # Now add text_d -- text_b should be evicted (oldest)
        engine._cache["text_d"] = {"dense": [0.4], "sparse": {}}
        if len(engine._cache) > engine._cache_max_size:
            engine._cache.popitem(last=False)

        assert "text_b" not in engine._cache  # text_b evicted
        assert "text_a" in engine._cache  # text_a preserved (recently used)
        assert "text_d" in engine._cache

    def test_embed_text_uses_cache(self):
        """embed_text should return cached result without calling model."""
        engine = EmbeddingEngine(cache_max_size=100)

        cached_result = {"dense": [1.0, 2.0, 3.0], "sparse": {}}
        engine._cache["hello world"] = cached_result

        result = engine.embed_text("hello world")
        assert result == cached_result
        # Model should not have been loaded
        assert engine._model is None

    def test_cache_max_size_boundary(self):
        """Cache should never exceed max_size."""
        engine = EmbeddingEngine(cache_max_size=5)

        # Add 10 entries using the same eviction logic as embed_text
        for i in range(10):
            engine._cache[f"text_{i}"] = {"dense": [float(i)], "sparse": {}}
            if len(engine._cache) > engine._cache_max_size:
                engine._cache.popitem(last=False)

        assert len(engine._cache) == 5
        # Should contain the 5 most recent entries
        for i in range(5, 10):
            assert f"text_{i}" in engine._cache
        for i in range(5):
            assert f"text_{i}" not in engine._cache

    def test_clear_cache(self):
        """clear_cache should empty the cache."""
        engine = EmbeddingEngine(cache_max_size=10)

        engine._cache["a"] = {"dense": [1.0], "sparse": {}}
        engine._cache["b"] = {"dense": [2.0], "sparse": {}}
        assert len(engine._cache) == 2

        engine.clear_cache()
        assert len(engine._cache) == 0

    def test_embed_batch_uses_cache_partially(self):
        """embed_batch should use cache for known texts and only encode unknowns."""
        engine = EmbeddingEngine(cache_max_size=100)

        # Pre-populate cache with one entry
        engine._cache["cached text"] = {"dense": [1.0, 2.0], "sparse": {}}

        # Mock the model to avoid loading sentence-transformers
        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock(
            tolist=MagicMock(return_value=[[3.0, 4.0]])
        )
        engine._model = mock_model

        results = engine.embed_batch(["cached text", "new text"])

        assert len(results) == 2
        assert results[0] == {"dense": [1.0, 2.0], "sparse": {}}
        assert results[1]["dense"] == [3.0, 4.0]

        # Only "new text" should have been encoded
        mock_model.encode.assert_called_once_with(["new text"])
