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
    # Metadata extracted during preprocessing (dates, currencies) without mutating text
    preprocessing_metadata: dict[str, Any] = field(default_factory=dict)
    proposal: GraphProposal | None = None
    resolutions: list[ResolutionResult] | None = None
    proposal_id: str | None = None
    route: ProposalRoute = ProposalRoute.AUTO
    stage: PipelineStage = PipelineStage.RAW_INPUT
    status: str = "processing"
    error: str | None = None
    clarification_needed: bool = False
    clarification_message: str = ""
    warnings: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Check invariants and return a list of violations (empty = valid)."""
        violations: list[str] = []

        # Status must be one of the known values
        valid_statuses = {"processing", "completed", "failed", "awaiting_review"}
        if self.status not in valid_statuses:
            violations.append(f"Unknown status '{self.status}'")

        # completed should not have an error
        if self.status == "completed" and self.error:
            violations.append(f"Status is 'completed' but error is set: {self.error}")

        # failed must have an error
        if self.status == "failed" and not self.error:
            violations.append("Status is 'failed' but no error message set")

        # clarification_needed requires a message
        if self.clarification_needed and not self.clarification_message:
            violations.append("clarification_needed=True but no clarification_message")

        # Can't be both failed and needing clarification
        if self.status == "failed" and self.clarification_needed:
            violations.append("Status is 'failed' but clarification_needed=True")

        # proposal_id without a proposal means something went wrong
        if self.proposal_id and not self.proposal:
            # This is valid after commit — proposal is stored, object may not be needed
            pass

        # Extraction stage should have processed_content if past preprocessing
        if self.stage >= PipelineStage.EXTRACTION and not self.processed_content and not self.error:
            violations.append("Past preprocessing but processed_content is empty")

        return violations


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
                # Validate state invariants between stages
                violations = state.validate()
                if violations:
                    logger.warning(
                        "State invariant violations after %s: %s",
                        stage_enum.name, "; ".join(violations),
                    )
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
        """Stage 2: Extract metadata (dates, currency), detect language.

        The raw text is passed through to the LLM without mutation so it
        retains natural language cues (e.g. "tomorrow" implies urgency).
        Resolved dates and currencies are stored as metadata that the
        archivist can reference alongside the original text.
        """
        text = state.raw_content.strip()

        # Extract date references as metadata without mutating text
        state.preprocessing_metadata["resolved_dates"] = self._extract_date_references(text)

        # Extract currency references as metadata without mutating text
        state.preprocessing_metadata["resolved_currencies"] = self._extract_currency_references(text)

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
            state.processed_content, state.capture_id,
            metadata=state.preprocessing_metadata if state.preprocessing_metadata else None,
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
        threshold = self._settings.auto_approve_threshold if self._settings else 0.85

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

        Failures are tracked in state.warnings rather than silently swallowed.
        """
        if state.error or not state.proposal_id:
            return state
        if state.route != ProposalRoute.AUTO:
            return state

        # Sequential: embeddings must complete before edge weights
        if not await self._run_substage("Embedding generation", self._generate_embeddings, state):
            state.warnings.append("Embedding generation failed — nodes may not appear in search")
            # Skip edge weights since they depend on embeddings
            state.warnings.append("Edge weight computation skipped (depends on embeddings)")
        else:
            if not await self._run_substage("Edge weight computation", self._compute_edge_weights, state):
                state.warnings.append("Edge weight computation failed — relationship strengths may be inaccurate")

        # Ensure every node orbits the central "You" node
        if not await self._run_substage("Graph connectivity", self._ensure_graph_connectivity, state):
            state.warnings.append("Graph connectivity check failed — some nodes may be orphaned")

        # Parallel: independent substages
        substage_names = ["Bridge detection", "Health scoring", "Notifications", "Truth layer"]
        substage_fns = [
            self._detect_bridges,
            self._recalculate_health,
            self._check_notification_triggers,
            self._cross_reference_truth_layer,
        ]

        results = await asyncio.gather(
            *(fn(state) for fn in substage_fns),
            return_exceptions=True,
        )

        for name, result in zip(substage_names, results):
            if isinstance(result, Exception):
                state.warnings.append(f"{name} failed: {type(result).__name__}")
                logger.warning("Post-commit substage %s failed: %s", name, result, exc_info=result)

        return state

    async def _run_substage(
        self,
        name: str,
        fn,
        state: PipelineState,
    ) -> bool:
        """Run a post-commit substage, returning True on success."""
        try:
            await fn(state)
            return True
        except Exception as e:
            logger.warning("Post-commit substage %s failed: %s", name, e, exc_info=True)
            return False

    # ================================================================
    # Utility methods
    # ================================================================

    async def _generate_embeddings(self, state: PipelineState) -> None:
        """Generate embeddings for all nodes in the committed proposal.

        Uses batch embedding and batch upsert for efficiency.
        """
        if not self._embedding_engine or not self._vector_store or not state.proposal:
            return

        # Get the committed nodes via repo method
        nodes = self._repo.get_nodes_by_capture_id(state.capture_id)
        if not nodes:
            return

        texts = []
        for node in nodes:
            text = f"{node['title']} {node['content']}" if node['content'] else node['title']
            # Append type-specific properties so they're searchable via vector search
            props = node.get("properties")
            if props:
                if isinstance(props, str):
                    import json as _json
                    try:
                        props = _json.loads(props)
                    except (ValueError, TypeError):
                        props = None
                if isinstance(props, dict) and props:
                    prop_parts = [f"{k}: {v}" for k, v in props.items() if v is not None]
                    if prop_parts:
                        text = f"{text} {' '.join(prop_parts)}"
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

    async def _compute_edge_weights(self, state: PipelineState) -> None:
        """Compute edge weights from cosine similarity of source/target embeddings.

        Uses batch embedding retrieval to minimize DB round-trips.
        """
        if not self._vector_store:
            return

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

    async def _detect_bridges(self, state: PipelineState) -> None:
        """Detect cross-network bridges for newly committed nodes.

        Runs in a thread since bridge discovery is CPU/IO-bound.
        """
        if not self._vector_store or not self._embedding_engine:
            return

        from memora.core.bridge_discovery import BridgeDiscovery

        bridge_detector = BridgeDiscovery(
            repo=self._repo,
            vector_store=self._vector_store,
            embedding_engine=self._embedding_engine,
        )

        node_ids = self._repo.get_node_ids_by_capture_id(state.capture_id)

        for node_id in node_ids:
            bridge_detector.discover_bridges_for_node(node_id)

    async def _recalculate_health(self, state: PipelineState) -> None:
        """Recalculate network health for networks affected by committed nodes."""
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

    async def _check_notification_triggers(self, state: PipelineState) -> None:
        """Check if newly committed nodes trigger notifications."""
        from memora.core.notifications import NotificationManager, DEADLINE_APPROACHING

        nm = NotificationManager(self._repo.get_truth_layer_conn())

        # Check for newly created commitments with approaching deadlines
        commitment_nodes = self._repo.get_commitment_nodes_by_capture_id(state.capture_id)

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

    # Node types that represent factual claims (not speculation/intent)
    _FACTUAL_NODE_TYPES = {"EVENT", "DECISION", "FINANCIAL_ITEM", "COMMITMENT"}

    # Phrases that indicate speculation or intent rather than fact
    _SPECULATIVE_MARKERS = re.compile(
        r"\b(might|maybe|could|possibly|thinking about|considering|"
        r"planning to|hoping to|want to|wish|probably|perhaps)\b",
        re.IGNORECASE,
    )

    async def _cross_reference_truth_layer(self, state: PipelineState) -> None:
        """Cross-reference new claims against verified facts in the Truth Layer."""
        from memora.core.truth_layer import TruthLayer

        truth_layer = TruthLayer(
            self._repo.get_truth_layer_conn(),
            embedding_engine=self._embedding_engine,
        )

        truth_nodes = self._repo.get_nodes_for_truth_check(state.capture_id)

        for node_data in truth_nodes:
            node_id, title, content = node_data["id"], node_data["title"], node_data["content"]
            node_type = node_data.get("node_type", "")

            # Build claim statement including flattened properties
            claim = content if content else title
            props = node_data.get("properties")
            if props:
                if isinstance(props, str):
                    import json as _json
                    try:
                        props = _json.loads(props)
                    except (ValueError, TypeError):
                        props = None
                if isinstance(props, dict) and props:
                    prop_parts = [f"{k}: {v}" for k, v in props.items() if v is not None]
                    if prop_parts:
                        claim = f"{claim} ({', '.join(prop_parts)})"

            contradictions = truth_layer.check_contradiction(claim, str(node_id))
            if contradictions:
                logger.info(
                    "Found %d potential contradiction(s) for node %s against Truth Layer",
                    len(contradictions),
                    node_id,
                )
                from memora.core.notifications import NotificationManager
                nm = NotificationManager(self._repo.get_truth_layer_conn())
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
            else:
                # Only auto-deposit factual node types with sufficient confidence
                # Skip speculative statements (e.g. "I might go to Paris")
                node_confidence = node_data.get("confidence", 0.0)
                is_speculative = bool(self._SPECULATIVE_MARKERS.search(claim))
                is_factual_type = node_type.upper() in self._FACTUAL_NODE_TYPES

                if is_factual_type and not is_speculative and node_confidence >= 0.8:
                    truth_layer.deposit_fact(
                        node_id=str(node_id),
                        statement=claim,
                        confidence=node_confidence,
                        source_capture_id=state.capture_id,
                        verified_by="pipeline_auto",
                        metadata={
                            "node_type": node_type,
                            "auto_deposited": True,
                        },
                    )
                else:
                    logger.debug(
                        "Skipping auto-deposit for node %s: type=%s speculative=%s confidence=%.2f",
                        node_id, node_type, is_speculative, node_confidence,
                    )

    async def _ensure_graph_connectivity(self, state: PipelineState) -> None:
        """Ensure every node from this capture connects to the central You node.

        For each new node without a direct edge to You, find the top-3 most
        similar existing nodes that DO have a path to You and link to them.
        If none are found, create a fallback RELATED_TO edge from You.
        """
        from memora.graph.repository import YOU_NODE_ID
        from memora.graph.models import Edge, EdgeType, EdgeCategory

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

    def _extract_date_references(self, text: str) -> list[dict[str, str]]:
        """Extract relative date phrases and resolve them without mutating text.

        Returns a list of {"phrase": ..., "resolved": ...} dicts.
        """
        today = datetime.now(timezone.utc).date()
        results: list[dict[str, str]] = []

        simple_patterns = {
            r"\btomorrow\b": today + timedelta(days=1),
            r"\byesterday\b": today - timedelta(days=1),
            r"\btoday\b": today,
        }

        for pattern, resolved_date in simple_patterns.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                results.append({
                    "phrase": match.group(),
                    "resolved": resolved_date.isoformat(),
                })

        # "next Monday/Tuesday/..." pattern
        day_names = [
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
        ]
        for i, day in enumerate(day_names):
            pattern = rf"\bnext\s+{day}\b"
            for match in re.finditer(pattern, text, re.IGNORECASE):
                current_weekday = today.weekday()
                days_ahead = (i - current_weekday + 7) % 7
                if days_ahead == 0:
                    days_ahead = 7
                target = today + timedelta(days=days_ahead)
                results.append({
                    "phrase": match.group(),
                    "resolved": target.isoformat(),
                })

        # "in N days" pattern
        for match in re.finditer(r"\bin\s+(\d+)\s+days?\b", text, re.IGNORECASE):
            n = int(match.group(1))
            target = today + timedelta(days=n)
            results.append({
                "phrase": match.group(),
                "resolved": target.isoformat(),
            })

        # "next week" pattern
        for match in re.finditer(r"\bnext\s+week\b", text, re.IGNORECASE):
            target = today + timedelta(weeks=1)
            results.append({
                "phrase": match.group(),
                "resolved": target.isoformat(),
            })

        # "end of month" pattern
        for match in re.finditer(r"\bend\s+of\s+(?:the\s+)?month\b", text, re.IGNORECASE):
            import calendar
            last_day = calendar.monthrange(today.year, today.month)[1]
            target = today.replace(day=last_day)
            results.append({
                "phrase": match.group(),
                "resolved": target.isoformat(),
            })

        return results

    def _extract_currency_references(self, text: str) -> list[dict[str, str]]:
        """Extract currency phrases and resolve them without mutating text.

        Returns a list of {"phrase": ..., "resolved": ...} dicts.
        """
        results: list[dict[str, str]] = []

        # "$50k" → "$50,000"
        for match in re.finditer(r"\$(\d+(?:\.\d+)?)k\b", text, re.IGNORECASE):
            amount = float(match.group(1)) * 1000
            results.append({
                "phrase": match.group(),
                "resolved": f"${amount:,.2f}",
            })

        # "$5-10k" range pattern
        for match in re.finditer(r"\$(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)k\b", text, re.IGNORECASE):
            lo = float(match.group(1)) * 1000
            hi = float(match.group(2)) * 1000
            results.append({
                "phrase": match.group(),
                "resolved": f"${lo:,.2f}-${hi:,.2f}",
            })

        # "N bucks" → "$N"
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s+bucks?\b", text, re.IGNORECASE):
            results.append({
                "phrase": match.group(),
                "resolved": f"${float(match.group(1)):.2f}",
            })

        # "N dollars" → "$N"
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s+dollars?\b", text, re.IGNORECASE):
            results.append({
                "phrase": match.group(),
                "resolved": f"${float(match.group(1)):.2f}",
            })

        return results

    def _detect_language(self, text: str) -> str:
        """Detect language of input text. Returns ISO 639-1 code.

        Uses langdetect if available, falls back to ASCII heuristic.
        """
        if not text:
            return "en"

        try:
            from langdetect import detect
            return detect(text)
        except ImportError:
            pass
        except Exception:
            pass

        # Fallback heuristic: check for non-ASCII character ratio
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        ascii_ratio = ascii_chars / len(text)

        if ascii_ratio > 0.9:
            return "en"

        # Can't determine — return unknown rather than assuming English
        return "und"
