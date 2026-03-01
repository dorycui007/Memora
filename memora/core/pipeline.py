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

import asyncio
import hashlib
import logging
import re
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
                you_node_id=repo.get_you_node_id(),
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
            stage_start = _time.perf_counter()
            logger.debug("Pipeline stage %s for capture %s", stage_enum.name, capture_id)
            try:
                state = await handler(state)
                elapsed = _time.perf_counter() - stage_start
                logger.info(
                    "Pipeline stage %s took %.2fs for capture %s",
                    stage_enum.name, elapsed, capture_id,
                )
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
                elapsed = _time.perf_counter() - stage_start
                state.error = f"Stage {stage_enum.name} failed: {str(e)}"
                state.status = "failed"
                _notify(stage_enum, "failed")
                logger.exception(
                    "Pipeline error at stage %s (after %.2fs)", stage_enum.name, elapsed
                )
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

        # Content hash — computed on raw_content to match the hash stored by the
        # capture API (dedup is handled by CLI/API before pipeline is invoked)
        state.content_hash = hashlib.sha256(state.raw_content.encode()).hexdigest()
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
        """Stage 4: Entity resolution against existing graph.

        Runs in a thread to unblock the event loop during CPU-bound
        embedding + DB work.
        """
        if not state.proposal or not state.proposal.nodes_to_create:
            return state

        state.resolutions = await asyncio.to_thread(
            self._resolver.resolve_nodes, state.proposal
        )
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
        """Stage 9: Generate embeddings, detect bridges, health recalc, notifications, truth layer.

        Embeddings and edge weights run sequentially (dependency), then the
        remaining four substages run in parallel via asyncio.gather().
        """
        if state.error or not state.proposal_id:
            return state
        if state.route != ProposalRoute.AUTO:
            return state

        # Sequential: embeddings must complete before edge weights
        await self._generate_embeddings(state)
        await self._compute_edge_weights(state)

        # Ensure every node orbits the central "You" node
        await self._ensure_graph_connectivity(state)

        # Parallel: independent substages
        await asyncio.gather(
            self._detect_bridges(state),
            self._recalculate_health(state),
            self._check_notification_triggers(state),
            self._cross_reference_truth_layer(state),
            return_exceptions=True,
        )

        return state

    # ================================================================
    # Utility methods
    # ================================================================

    async def _generate_embeddings(self, state: PipelineState) -> None:
        """Generate embeddings for all nodes in the committed proposal.

        Uses batch embedding and batch upsert for efficiency.
        """
        if not self._embedding_engine or not self._vector_store or not state.proposal:
            return

        try:
            # Get the committed nodes via repo method
            nodes = self._repo.get_nodes_by_capture_id(state.capture_id)
            if not nodes:
                return

            texts = []
            for node in nodes:
                text = f"{node['title']} {node['content']}" if node['content'] else node['title']
                texts.append(text)

            embeddings = self._embedding_engine.embed_batch(texts)

            records = []
            for node, text, emb in zip(nodes, texts, embeddings):
                records.append({
                    "node_id": node["id"],
                    "content": text,
                    "node_type": node["node_type"],
                    "networks": node["networks"] if node["networks"] else [],
                    "vector": emb["dense"],
                })

            self._vector_store.batch_upsert_embeddings(records)
            logger.info("Generated embeddings for %d nodes", len(nodes))
        except Exception:
            logger.warning("Embedding generation failed", exc_info=True)

    async def _compute_edge_weights(self, state: PipelineState) -> None:
        """Compute edge weights from cosine similarity of source/target embeddings.

        Uses batch embedding retrieval to minimize DB round-trips.
        """
        if not self._vector_store:
            return

        try:
            from memora.vector.embeddings import cosine_similarity

            # Get all node IDs for this capture
            node_ids = set(self._repo.get_node_ids_by_capture_id(state.capture_id))
            if not node_ids:
                return

            # Get all edges touching these nodes
            edge_rows = self._repo.get_edges_for_node_ids(node_ids)
            if not edge_rows:
                return

            # Collect all unique endpoint node IDs
            all_endpoint_ids: set[str] = set()
            for edge in edge_rows:
                all_endpoint_ids.add(edge["source_id"])
                all_endpoint_ids.add(edge["target_id"])

            # Batch fetch all embeddings
            embedding_map = self._vector_store.get_embeddings_batch(list(all_endpoint_ids))

            updated = 0
            for edge in edge_rows:
                edge_id, source_id, target_id = edge["id"], edge["source_id"], edge["target_id"]
                src_vec = embedding_map.get(source_id)
                tgt_vec = embedding_map.get(target_id)
                if src_vec is None or tgt_vec is None:
                    continue
                weight = max(0.0, cosine_similarity(src_vec, tgt_vec))
                self._repo.update_edge_weight(edge_id, weight)
                updated += 1

            logger.info("Updated weights for %d edges", updated)
        except Exception:
            logger.warning("Edge weight computation failed", exc_info=True)

    async def _detect_bridges(self, state: PipelineState) -> None:
        """Detect cross-network bridges for newly committed nodes.

        Runs in a thread since bridge discovery is CPU/IO-bound.
        """
        if not self._vector_store or not self._embedding_engine:
            return

        try:
            from memora.core.bridge_discovery import BridgeDiscovery

            bridge_detector = BridgeDiscovery(
                repo=self._repo,
                vector_store=self._vector_store,
                embedding_engine=self._embedding_engine,
            )

            node_ids = self._repo.get_node_ids_by_capture_id(state.capture_id)

            for node_id in node_ids:
                bridge_detector.discover_bridges_for_node(node_id)
        except Exception:
            logger.warning("Bridge detection failed", exc_info=True)

    async def _recalculate_health(self, state: PipelineState) -> None:
        """Recalculate network health for networks affected by committed nodes."""
        try:
            from memora.core.health_scoring import HealthScoring

            affected_networks = self._repo.get_networks_by_capture_id(state.capture_id)

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
            commitment_nodes = self._repo.get_commitment_nodes_by_capture_id(state.capture_id)

            from datetime import datetime, timedelta, timezone
            now = datetime.now(timezone.utc)
            for commitment in commitment_nodes:
                node_id, title, due_date_str = commitment["id"], commitment["title"], commitment["due_date"]
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

            truth_nodes = self._repo.get_nodes_for_truth_check(state.capture_id)

            for node_data in truth_nodes:
                node_id, title, content = node_data["id"], node_data["title"], node_data["content"]
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

    async def _ensure_graph_connectivity(self, state: PipelineState) -> None:
        """Ensure every node from this capture connects to the central You node.

        For each new node without a direct edge to You, find the top-3 most
        similar existing nodes that DO have a path to You and link to them.
        If none are found, create a fallback RELATED_TO edge from You.
        """
        from memora.graph.repository import YOU_NODE_ID
        from memora.graph.models import Edge, EdgeType, EdgeCategory

        try:
            node_ids = self._repo.get_node_ids_by_capture_id(state.capture_id)
            if not node_ids:
                return

            # Get all edges touching these nodes
            edges = self._repo.get_edges_for_node_ids(set(node_ids))

            # Find which nodes already have a direct edge to/from You
            connected_to_you: set[str] = set()
            for edge in edges:
                if edge["source_id"] == YOU_NODE_ID:
                    connected_to_you.add(edge["target_id"])
                elif edge["target_id"] == YOU_NODE_ID:
                    connected_to_you.add(edge["source_id"])

            orphans = [nid for nid in node_ids if nid not in connected_to_you and nid != YOU_NODE_ID]
            if not orphans:
                return

            linked = 0
            for orphan_id in orphans:
                bridged = False

                # Try to find similar existing nodes connected to You
                if self._vector_store and self._embedding_engine:
                    embedding_map = self._vector_store.get_embeddings_batch([orphan_id])
                    orphan_vec = embedding_map.get(orphan_id)

                    if orphan_vec is not None:
                        from memora.vector.embeddings import cosine_similarity

                        results = self._vector_store.dense_search(orphan_vec, top_k=10)
                        for result in results:
                            r = result.to_dict()
                            candidate_id = r.get("node_id", "")
                            if candidate_id == orphan_id or candidate_id in node_ids:
                                continue
                            # Check if candidate is connected to You
                            candidate_edges = self._repo.get_edges_for_node_ids({candidate_id})
                            has_you_path = any(
                                e["source_id"] == YOU_NODE_ID or e["target_id"] == YOU_NODE_ID
                                for e in candidate_edges
                            )
                            if has_you_path:
                                score = max(0.0, min(1.0, r.get("score", 0.5)))
                                self._repo.create_edge(Edge(
                                    source_id=UUID(orphan_id),
                                    target_id=UUID(candidate_id),
                                    edge_type=EdgeType.RELATED_TO,
                                    edge_category=EdgeCategory.ASSOCIATIVE,
                                    confidence=score,
                                    weight=score,
                                ))
                                bridged = True
                                linked += 1
                                break  # one bridge is enough

                # Fallback: connect directly to You
                if not bridged:
                    self._repo.create_edge(Edge(
                        source_id=UUID(YOU_NODE_ID),
                        target_id=UUID(orphan_id),
                        edge_type=EdgeType.RELATED_TO,
                        edge_category=EdgeCategory.ASSOCIATIVE,
                        confidence=0.5,
                        weight=0.5,
                    ))
                    linked += 1

            if linked:
                logger.info("Graph connectivity: linked %d orphan node(s) to You", linked)
        except Exception:
            logger.warning("Graph connectivity enforcement failed", exc_info=True)

    def _normalize_dates(self, text: str) -> str:
        """Convert common relative date phrases to ISO format."""
        today = datetime.now(timezone.utc).date()

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
        # "$50k" → "$50,000" (require $ prefix to avoid corrupting non-financial data like "50kb")
        text = re.sub(
            r"\$(\d+(?:\.\d+)?)k\b",
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
