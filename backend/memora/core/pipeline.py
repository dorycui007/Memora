"""Extraction Pipeline — 9-stage async pipeline from raw text to graph commit.

Stages:
1. Raw input capture
2. Preprocessing (normalize, detect language, dedup)
3. Archivist extraction (LLM → GraphProposal)
4. Entity resolution (multi-signal matching)
5. Proposal assembly (apply merges)
6. Validation gate (confidence routing)
7. Human review / auto-approve
8. Graph commit (atomic transaction)
9. Post-commit processing (embeddings, bridges, truth layer)
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
from typing import Any, Callable
from uuid import UUID

from memora.agents.archivist import ArchivistAgent
from memora.config import Settings
from memora.core.entity_resolution import EntityResolver, ResolutionOutcome, ResolutionResult
from memora.graph.models import GraphProposal, ProposalRoute
from memora.graph.repository import GraphRepository
from memora.vector.embeddings import EmbeddingEngine
from memora.vector.store import VectorStore

logger = logging.getLogger(__name__)


class PipelineStage(IntEnum):
    RAW_INPUT = 1
    PREPROCESSING = 2
    EXTRACTION = 3
    ENTITY_RESOLUTION = 4
    PROPOSAL_ASSEMBLY = 5
    VALIDATION_GATE = 6
    REVIEW = 7
    GRAPH_COMMIT = 8
    POST_COMMIT = 9


STAGE_NAMES = {
    PipelineStage.RAW_INPUT: "Raw Input",
    PipelineStage.PREPROCESSING: "Preprocessing",
    PipelineStage.EXTRACTION: "Archivist Extraction",
    PipelineStage.ENTITY_RESOLUTION: "Entity Resolution",
    PipelineStage.PROPOSAL_ASSEMBLY: "Proposal Assembly",
    PipelineStage.VALIDATION_GATE: "Validation Gate",
    PipelineStage.REVIEW: "Review",
    PipelineStage.GRAPH_COMMIT: "Graph Commit",
    PipelineStage.POST_COMMIT: "Post-Commit Processing",
}


@dataclass
class PipelineState:
    """Mutable state carried through the pipeline."""

    capture_id: str
    raw_content: str
    processed_content: str = ""
    content_hash: str = ""
    language: str = "en"
    is_duplicate: bool = False
    proposal: GraphProposal | None = None
    resolutions: list[ResolutionResult] | None = None
    proposal_id: str | None = None
    route: ProposalRoute = ProposalRoute.AUTO
    stage: PipelineStage = PipelineStage.RAW_INPUT
    status: str = "processing"
    error: str | None = None
    clarification_needed: bool = False
    clarification_message: str = ""


class ExtractionPipeline:
    """9-stage async pipeline from raw text to graph commit."""

    def __init__(
        self,
        repo: GraphRepository,
        vector_store: VectorStore | None = None,
        embedding_engine: EmbeddingEngine | None = None,
        settings: Settings | None = None,
        archivist: ArchivistAgent | None = None,
        resolver: EntityResolver | None = None,
    ) -> None:
        self._repo = repo
        self._vector_store = vector_store
        self._embedding_engine = embedding_engine
        self._settings = settings

        # Initialize archivist if API key available
        if archivist:
            self._archivist = archivist
        elif settings and settings.openai_api_key:
            self._archivist = ArchivistAgent(
                api_key=settings.openai_api_key,
                vector_store=vector_store,
                embedding_engine=embedding_engine,
            )
        else:
            self._archivist = None

        # Initialize entity resolver
        if resolver:
            self._resolver = resolver
        else:
            openai_client = None
            if settings and settings.openai_api_key:
                import openai
                openai_client = openai.OpenAI(api_key=settings.openai_api_key)
            self._resolver = EntityResolver(
                repo=repo,
                vector_store=vector_store,
                embedding_engine=embedding_engine,
                llm_client=openai_client,
            )

    async def run(
        self,
        capture_id: str,
        raw_content: str,
        on_stage: Callable[[PipelineStage, str], None] | None = None,
    ) -> PipelineState:
        """Execute the full pipeline. Returns final state.

        Args:
            capture_id: UUID string of the capture.
            raw_content: The raw text to process.
            on_stage: Optional callback invoked at each stage transition.
                      Receives (stage_enum, status) where status is
                      "running", "done", "failed", or "skipped".
        """
        state = PipelineState(capture_id=capture_id, raw_content=raw_content)
        logger.info("Pipeline started for capture %s", capture_id)

        def _notify(stage: PipelineStage, status: str) -> None:
            if on_stage:
                try:
                    on_stage(stage, status)
                except Exception:
                    pass  # never let callback errors break the pipeline

        stages = [
            (PipelineStage.PREPROCESSING, self._preprocess),
            (PipelineStage.EXTRACTION, self._extract),
            (PipelineStage.ENTITY_RESOLUTION, self._resolve_entities),
            (PipelineStage.PROPOSAL_ASSEMBLY, self._assemble_proposal),
            (PipelineStage.VALIDATION_GATE, self._validation_gate),
            (PipelineStage.REVIEW, self._review),
            (PipelineStage.GRAPH_COMMIT, self._commit),
            (PipelineStage.POST_COMMIT, self._post_commit),
        ]

        for stage_enum, handler in stages:
            state.stage = stage_enum
            _notify(stage_enum, "running")
            logger.debug("Pipeline stage %s for capture %s", stage_enum.name, capture_id)
            try:
                state = await handler(state)
                if state.error:
                    state.status = "failed"
                    _notify(stage_enum, "failed")
                    logger.error(
                        "Pipeline failed at %s: %s", stage_enum.name, state.error
                    )
                    break
                if state.clarification_needed:
                    state.status = "awaiting_review"
                    _notify(stage_enum, "done")
                    break
                _notify(stage_enum, "done")
            except Exception as e:
                state.error = f"Stage {stage_enum.name} failed: {str(e)}"
                state.status = "failed"
                _notify(stage_enum, "failed")
                logger.exception("Pipeline error at stage %s", stage_enum.name)
                break

        if not state.error and not state.clarification_needed:
            state.status = "completed"

        logger.info(
            "Pipeline finished for capture %s: stage=%s status=%s",
            capture_id, state.stage.name, state.status,
        )
        return state

    # ================================================================
    # Stage implementations
    # ================================================================

    async def _preprocess(self, state: PipelineState) -> PipelineState:
        """Stage 2: Text normalization, language detection, dedup."""
        text = state.raw_content.strip()

        # Date normalization
        text = self._normalize_dates(text)

        # Currency normalization
        text = self._normalize_currency(text)

        # Language detection
        state.language = self._detect_language(text)

        # Content hash (dedup is handled by CLI/API before pipeline is invoked)
        state.content_hash = hashlib.sha256(text.encode()).hexdigest()
        state.processed_content = text
        return state

    async def _extract(self, state: PipelineState) -> PipelineState:
        """Stage 3: Call Archivist agent for LLM extraction."""
        if not self._archivist:
            state.error = "Archivist agent not configured (missing API key)"
            return state

        result = await self._archivist.extract(
            state.processed_content, state.capture_id
        )

        if result.clarification_needed:
            state.clarification_needed = True
            state.clarification_message = result.clarification_message
            return state

        if result.proposal is None:
            state.error = "Archivist extraction returned no proposal"
            return state

        state.proposal = result.proposal
        return state

    async def _resolve_entities(self, state: PipelineState) -> PipelineState:
        """Stage 4: Entity resolution against existing graph."""
        if not state.proposal or not state.proposal.nodes_to_create:
            return state

        state.resolutions = self._resolver.resolve_nodes(state.proposal)
        return state

    async def _assemble_proposal(self, state: PipelineState) -> PipelineState:
        """Stage 5: Apply merge decisions and finalize proposal."""
        if not state.proposal or not state.resolutions:
            return state

        state.proposal = self._resolver.apply_merges(
            state.proposal, state.resolutions
        )
        return state

    async def _validation_gate(self, state: PipelineState) -> PipelineState:
        """Stage 6: Route to auto-approve, digest, or explicit review."""
        if not state.proposal:
            return state

        confidence = state.proposal.confidence
        threshold = 0.85
        if self._settings:
            threshold = self._settings.auto_approve_threshold

        # Check for high-impact changes that require explicit review
        has_merges = any(
            r.outcome == ResolutionOutcome.MERGE
            for r in (state.resolutions or [])
        )
        has_deferred = any(
            r.outcome == ResolutionOutcome.DEFER
            for r in (state.resolutions or [])
        )

        if has_merges or has_deferred:
            state.route = ProposalRoute.EXPLICIT
        elif confidence >= threshold:
            state.route = ProposalRoute.AUTO
        else:
            state.route = ProposalRoute.DIGEST

        return state

    async def _review(self, state: PipelineState) -> PipelineState:
        """Stage 7: Store proposal, auto-approve if route=AUTO."""
        if not state.proposal:
            return state

        proposal_id = self._repo.create_proposal(
            state.proposal,
            agent_id="archivist",
            route=state.route,
        )
        state.proposal_id = str(proposal_id)

        if state.route != ProposalRoute.AUTO:
            state.status = "awaiting_review"

        return state

    async def _commit(self, state: PipelineState) -> PipelineState:
        """Stage 8: Atomic graph commit (only for auto-approved)."""
        if not state.proposal_id:
            return state
        if state.route != ProposalRoute.AUTO:
            return state

        success = self._repo.commit_proposal(UUID(state.proposal_id))
        if not success:
            state.error = "Graph commit failed"
        return state

    async def _post_commit(self, state: PipelineState) -> PipelineState:
        """Stage 9: Generate embeddings, detect bridges, health recalc, notifications, truth layer."""
        if state.error or not state.proposal_id:
            return state
        if state.route != ProposalRoute.AUTO:
            return state

        # Generate embeddings for new/updated nodes
        await self._generate_embeddings(state)

        # Compute edge weights from node embedding similarity
        await self._compute_edge_weights(state)

        # Bridge detection (cross-network)
        await self._detect_bridges(state)

        # Network health recalculation for affected networks
        await self._recalculate_health(state)

        # Notification trigger checks (deadlines, relationship decay, goal drift)
        await self._check_notification_triggers(state)

        # Truth Layer cross-reference for new claims
        await self._cross_reference_truth_layer(state)

        return state

    # ================================================================
    # Utility methods
    # ================================================================

    async def _generate_embeddings(self, state: PipelineState) -> None:
        """Generate embeddings for all nodes in the committed proposal."""
        if not self._embedding_engine or not self._vector_store or not state.proposal:
            return

        try:
            # Get the committed nodes (proposal data has temp_ids, we need real IDs)
            # Query recently created nodes for this capture
            rows = self._repo._conn.execute(
                "SELECT id, node_type, title, content, networks FROM nodes "
                "WHERE source_capture_id = ? AND deleted = FALSE",
                [state.capture_id],
            ).fetchall()

            for row in rows:
                node_id, node_type, title, content, networks = row
                text = f"{title} {content}" if content else title
                embedding = self._embedding_engine.embed_text(text)
                self._vector_store.upsert_embedding(
                    node_id=node_id,
                    content=text,
                    node_type=node_type,
                    networks=networks if networks else [],
                    vector=embedding["dense"],
                )

            logger.info("Generated embeddings for %d nodes", len(rows))
        except Exception:
            logger.warning("Embedding generation failed", exc_info=True)

    async def _compute_edge_weights(self, state: PipelineState) -> None:
        """Compute edge weights from cosine similarity of source/target embeddings."""
        if not self._vector_store:
            return

        try:
            from memora.vector.embeddings import cosine_similarity

            # Get all node IDs for this capture
            node_rows = self._repo._conn.execute(
                "SELECT id FROM nodes WHERE source_capture_id = ? AND deleted = FALSE",
                [state.capture_id],
            ).fetchall()
            node_ids = {row[0] for row in node_rows}
            if not node_ids:
                return

            # Get all edges touching these nodes
            placeholders = ", ".join(["?"] * len(node_ids))
            edge_rows = self._repo._conn.execute(
                f"SELECT id, source_id, target_id FROM edges "
                f"WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
                list(node_ids) + list(node_ids),
            ).fetchall()

            updated = 0
            for edge_id, source_id, target_id in edge_rows:
                src_vec = self._vector_store.get_embedding(source_id)
                tgt_vec = self._vector_store.get_embedding(target_id)
                if src_vec is None or tgt_vec is None:
                    continue
                weight = max(0.0, cosine_similarity(src_vec, tgt_vec))
                self._repo.update_edge_weight(edge_id, weight)
                updated += 1

            logger.info("Updated weights for %d edges", updated)
        except Exception:
            logger.warning("Edge weight computation failed", exc_info=True)

    async def _detect_bridges(self, state: PipelineState) -> None:
        """Detect cross-network bridges for newly committed nodes."""
        if not self._vector_store or not self._embedding_engine:
            return

        try:
            from memora.core.bridge_discovery import BridgeDiscovery

            bridge_detector = BridgeDiscovery(
                repo=self._repo,
                vector_store=self._vector_store,
                embedding_engine=self._embedding_engine,
            )

            rows = self._repo._conn.execute(
                "SELECT id FROM nodes WHERE source_capture_id = ? AND deleted = FALSE",
                [state.capture_id],
            ).fetchall()

            for row in rows:
                bridge_detector.discover_bridges_for_node(row[0])
        except Exception:
            logger.warning("Bridge detection failed", exc_info=True)

    async def _recalculate_health(self, state: PipelineState) -> None:
        """Recalculate network health for networks affected by committed nodes."""
        try:
            from memora.core.health_scoring import HealthScoring

            rows = self._repo._conn.execute(
                "SELECT networks FROM nodes WHERE source_capture_id = ? AND deleted = FALSE",
                [state.capture_id],
            ).fetchall()

            affected_networks: set[str] = set()
            for row in rows:
                networks = row[0] if row[0] else []
                for net in networks:
                    affected_networks.add(net)

            if affected_networks:
                scorer = HealthScoring(self._repo)
                for network in affected_networks:
                    scorer.compute_network_health(network)
                logger.info(
                    "Recalculated health for %d network(s): %s",
                    len(affected_networks),
                    ", ".join(affected_networks),
                )
        except Exception:
            logger.warning("Network health recalculation failed", exc_info=True)

    async def _check_notification_triggers(self, state: PipelineState) -> None:
        """Check if newly committed nodes trigger notifications."""
        try:
            from memora.core.notifications import NotificationManager, DEADLINE_APPROACHING

            nm = NotificationManager(self._repo._conn)

            # Check for newly created commitments with approaching deadlines
            rows = self._repo._conn.execute(
                """SELECT id, title, json_extract_string(properties, '$.due_date') as due_date
                   FROM nodes
                   WHERE source_capture_id = ?
                     AND deleted = FALSE
                     AND node_type = 'COMMITMENT'
                     AND json_extract_string(properties, '$.status') = 'open'
                     AND json_extract_string(properties, '$.due_date') IS NOT NULL""",
                [state.capture_id],
            ).fetchall()

            from datetime import datetime, timedelta
            now = datetime.utcnow()
            for row in rows:
                node_id, title, due_date_str = row
                try:
                    due_date = datetime.fromisoformat(due_date_str)
                    days_until = (due_date - now).days
                    if 0 <= days_until <= 7:
                        nm.create_notification(
                            type=DEADLINE_APPROACHING,
                            message=f"New commitment \"{title}\" is due in {days_until} day(s)",
                            related_node_ids=[str(node_id)],
                            priority="high" if days_until <= 1 else "medium",
                            trigger_condition="post_commit_deadline_check",
                        )
                except (ValueError, TypeError):
                    pass

            logger.debug("Post-commit notification triggers checked")
        except Exception:
            logger.warning("Notification trigger check failed", exc_info=True)

    async def _cross_reference_truth_layer(self, state: PipelineState) -> None:
        """Cross-reference new claims against verified facts in the Truth Layer."""
        try:
            from memora.core.truth_layer import TruthLayer

            truth_layer = TruthLayer(self._repo._conn)

            rows = self._repo._conn.execute(
                "SELECT id, title, content FROM nodes WHERE source_capture_id = ? AND deleted = FALSE",
                [state.capture_id],
            ).fetchall()

            for row in rows:
                node_id, title, content = row
                claim = content if content else title
                contradictions = truth_layer.check_contradiction(claim, str(node_id))
                if contradictions:
                    logger.info(
                        "Found %d potential contradiction(s) for node %s against Truth Layer",
                        len(contradictions),
                        node_id,
                    )
                    from memora.core.notifications import NotificationManager
                    nm = NotificationManager(self._repo._conn)
                    fact_summaries = "; ".join(
                        c.get("statement", "")[:60] for c in contradictions[:3]
                    )
                    nm.create_notification(
                        type="truth_contradiction",
                        message=f"Node \"{title}\" may contradict existing facts: {fact_summaries}",
                        related_node_ids=[str(node_id)],
                        priority="high",
                        trigger_condition="truth_layer_cross_reference",
                    )
        except Exception:
            logger.warning("Truth Layer cross-reference failed", exc_info=True)

    def _normalize_dates(self, text: str) -> str:
        """Convert common relative date phrases to ISO format."""
        today = datetime.utcnow().date()

        replacements = {
            r"\btomorrow\b": (today + timedelta(days=1)).isoformat(),
            r"\byesterday\b": (today - timedelta(days=1)).isoformat(),
            r"\btoday\b": today.isoformat(),
        }

        # "next Monday/Tuesday/..." pattern
        day_names = [
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
        ]
        for i, day in enumerate(day_names):
            pattern = rf"\bnext\s+{day}\b"
            current_weekday = today.weekday()
            days_ahead = (i - current_weekday + 7) % 7
            if days_ahead == 0:
                days_ahead = 7
            target = today + timedelta(days=days_ahead)
            replacements[pattern] = target.isoformat()

        # "in N days" pattern
        in_days_match = re.search(r"\bin\s+(\d+)\s+days?\b", text, re.IGNORECASE)
        if in_days_match:
            n = int(in_days_match.group(1))
            target = today + timedelta(days=n)
            text = text[:in_days_match.start()] + target.isoformat() + text[in_days_match.end():]

        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        return text

    def _normalize_currency(self, text: str) -> str:
        """Normalize common currency mentions."""
        # "$50k" or "50k" → "$50,000"
        text = re.sub(
            r"\$?(\d+(?:\.\d+)?)k\b",
            lambda m: f"${float(m.group(1)) * 1000:,.2f}",
            text,
            flags=re.IGNORECASE,
        )

        # "N bucks" → "$N.00"
        text = re.sub(
            r"(\d+(?:\.\d+)?)\s+bucks?\b",
            lambda m: f"${float(m.group(1)):.2f}",
            text,
            flags=re.IGNORECASE,
        )

        # "N dollars" → "$N.00"
        text = re.sub(
            r"(\d+(?:\.\d+)?)\s+dollars?\b",
            lambda m: f"${float(m.group(1)):.2f}",
            text,
            flags=re.IGNORECASE,
        )

        return text

    def _detect_language(self, text: str) -> str:
        """Simple language detection. Returns ISO 639-1 code."""
        # Heuristic: check ASCII ratio
        if not text:
            return "en"

        ascii_chars = sum(1 for c in text if ord(c) < 128)
        ascii_ratio = ascii_chars / len(text)

        if ascii_ratio > 0.9:
            return "en"

        # Could add langdetect or similar for non-English detection
        return "en"
