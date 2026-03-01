"""Entity Resolution — multi-signal deduplication and merge engine.

Resolves proposed nodes against existing graph nodes using 6 weighted signals:
exact name match, embedding similarity, network overlap, temporal proximity,
shared relationships, and optional LLM adjudication.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from memora.core.retry import call_with_retry
from memora.graph.models import GraphProposal, NodeProposal, NodeUpdate
from memora.graph.repository import GraphRepository
from memora.vector.embeddings import EmbeddingEngine
from memora.vector.store import VectorStore

logger = logging.getLogger(__name__)


class ResolutionOutcome(str, Enum):
    MERGE = "merge"
    CREATE = "create"
    LINK = "link"
    DEFER = "defer"


@dataclass
class ResolutionCandidate:
    """A candidate existing node that might match a proposed node."""

    existing_node_id: str
    existing_title: str
    existing_node_type: str
    existing_networks: list[str] = field(default_factory=list)
    signals: dict[str, float] = field(default_factory=dict)
    combined_score: float = 0.0
    outcome: ResolutionOutcome = ResolutionOutcome.CREATE


@dataclass
class ResolutionResult:
    """Resolution result for a single proposed node."""

    proposed_temp_id: str
    proposed_title: str
    candidates: list[ResolutionCandidate] = field(default_factory=list)
    chosen: ResolutionCandidate | None = None
    outcome: ResolutionOutcome = ResolutionOutcome.CREATE
    audit_log: list[str] = field(default_factory=list)


class EntityResolver:
    """Multi-signal entity resolution engine."""

    # Signal weights
    WEIGHTS = {
        "exact_name": 0.95,
        "embedding_similarity": 0.80,
        "same_network": 0.15,
        "temporal_proximity": 0.10,
        "shared_relationships": 0.20,
        "llm_adjudication": 0.90,
    }

    EMBEDDING_THRESHOLD = 0.92
    MERGE_THRESHOLD = 0.85
    CREATE_THRESHOLD = 0.60
    TEMPORAL_WINDOW_DAYS = 7

    def __init__(
        self,
        repo: GraphRepository,
        vector_store: VectorStore | None = None,
        embedding_engine: EmbeddingEngine | None = None,
        llm_client: Any = None,
    ) -> None:
        self._repo = repo
        self._vector_store = vector_store
        self._embedding_engine = embedding_engine
        self._llm_client = llm_client

    def resolve_nodes(
        self,
        proposal: GraphProposal,
    ) -> list[ResolutionResult]:
        """Resolve all proposed nodes against the existing graph.

        Uses batch prefetching for embeddings, created_at timestamps,
        and adjacency data to minimize DB round-trips.
        """
        nodes = proposal.nodes_to_create
        if not nodes:
            return []

        # Batch embedding search for all nodes at once
        similar_map = self._find_similar_nodes_batch(nodes)

        # Batch exact match search
        exact_map: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            exact_map[node.temp_id] = self._find_exact_matches(node)

        # Collect all candidate IDs across all nodes
        all_candidate_ids: set[str] = set()
        for node in nodes:
            for match in exact_map.get(node.temp_id, []):
                all_candidate_ids.add(match["id"])
            for sim in similar_map.get(node.temp_id, []):
                all_candidate_ids.add(sim["node_id"])

        # Batch prefetch created_at timestamps
        created_at_map: dict[str, datetime] = {}
        if all_candidate_ids:
            created_at_map = self._repo.get_node_created_at_batch(list(all_candidate_ids))

        # Batch prefetch adjacency
        adjacency_map: dict[str, set[str]] = {}
        if all_candidate_ids:
            edge_rows = self._repo.get_edges_for_node_ids(all_candidate_ids)
            for edge in edge_rows:
                src, tgt = edge["source_id"], edge["target_id"]
                adjacency_map.setdefault(src, set()).add(tgt)
                adjacency_map.setdefault(tgt, set()).add(src)

        # Resolve each node using prefetched data
        results = []
        for node in nodes:
            result = self._resolve_single(
                node, proposal,
                exact_matches=exact_map.get(node.temp_id, []),
                similar_nodes=similar_map.get(node.temp_id, []),
                created_at_map=created_at_map,
                adjacency_map=adjacency_map,
            )
            results.append(result)
        return results

    def _resolve_single(
        self,
        node: NodeProposal,
        proposal: GraphProposal,
        exact_matches: list[dict[str, Any]] | None = None,
        similar_nodes: list[dict[str, Any]] | None = None,
        created_at_map: dict[str, datetime] | None = None,
        adjacency_map: dict[str, set[str]] | None = None,
    ) -> ResolutionResult:
        """Resolve a single proposed node."""
        result = ResolutionResult(
            proposed_temp_id=node.temp_id,
            proposed_title=node.title,
        )
        audit = result.audit_log

        # 1. Find exact name matches in DB
        if exact_matches is None:
            exact_matches = self._find_exact_matches(node)
        audit.append(f"Exact name search: {len(exact_matches)} matches for '{node.title}'")

        # 2. Find embedding-similar nodes
        if similar_nodes is None:
            similar_nodes = self._find_similar_nodes(node)
        audit.append(f"Embedding search: {len(similar_nodes)} similar nodes")

        # 3. Build candidate list from union
        candidates_map: dict[str, ResolutionCandidate] = {}

        for match in exact_matches:
            nid = match["id"]
            candidates_map[nid] = ResolutionCandidate(
                existing_node_id=nid,
                existing_title=match["title"],
                existing_node_type=match["node_type"],
                existing_networks=match.get("networks", []),
            )

        for sim in similar_nodes:
            nid = sim["node_id"]
            if nid not in candidates_map:
                candidates_map[nid] = ResolutionCandidate(
                    existing_node_id=nid,
                    existing_title=sim.get("content", ""),
                    existing_node_type=sim.get("node_type", ""),
                    existing_networks=sim.get("networks", []),
                )

        candidates = list(candidates_map.values())

        # Never merge into the central "You" node
        from memora.graph.repository import YOU_NODE_ID
        candidates = [c for c in candidates if c.existing_node_id != YOU_NODE_ID]

        if not candidates:
            result.outcome = ResolutionOutcome.CREATE
            audit.append("No candidates found — creating new node")
            return result

        # 4. Score each candidate across all non-LLM signals
        for candidate in candidates:
            self._score_exact_name(candidate, node)
            self._score_embedding(candidate, similar_nodes)
            self._score_network_overlap(candidate, node)
            self._score_temporal(
                candidate, node,
                created_at=created_at_map.get(candidate.existing_node_id) if created_at_map else None,
            )
            self._score_shared_relationships(
                candidate, node, proposal,
                existing_neighbors=adjacency_map.get(candidate.existing_node_id) if adjacency_map else None,
            )
            candidate.combined_score = self._weighted_sum(candidate.signals)

        # 4b. Early-exit: perfect exact name match forces MERGE
        #     A perfect name match (score 1.0) means identical title+type.
        #     Without this, zero signals for embedding/network/temporal/relationships
        #     dilute the weighted average below the merge threshold.
        for candidate in candidates:
            if candidate.signals.get("exact_name", 0.0) >= 1.0:
                candidate.combined_score = 1.0
                candidate.outcome = ResolutionOutcome.MERGE
                result.outcome = ResolutionOutcome.MERGE
                result.chosen = candidate
                result.candidates = candidates
                audit.append(
                    f"MERGE (exact name): '{node.title}' → '{candidate.existing_title}' "
                    f"(exact_name=1.0, forced merge)"
                )
                return result

        # 5. LLM adjudication for ambiguous cases — run in parallel
        ambiguous_pairs: list[tuple[NodeProposal, ResolutionCandidate]] = []
        for candidate in candidates:
            if self.CREATE_THRESHOLD <= candidate.combined_score < self.MERGE_THRESHOLD:
                if self._llm_client:
                    ambiguous_pairs.append((node, candidate))

        if ambiguous_pairs:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(self._llm_adjudicate, n, c): c
                    for n, c in ambiguous_pairs
                }
                for future in concurrent.futures.as_completed(futures):
                    cand = futures[future]
                    try:
                        llm_score = future.result()
                    except Exception:
                        llm_score = 0.5
                    cand.signals["llm_adjudication"] = llm_score
                    cand.combined_score = self._weighted_sum(cand.signals)
                    audit.append(
                        f"LLM adjudication for '{cand.existing_title}': {llm_score:.2f}"
                    )

        # 6. Determine outcome for best candidate
        candidates.sort(key=lambda c: c.combined_score, reverse=True)
        result.candidates = candidates
        best = candidates[0]

        if best.combined_score >= self.MERGE_THRESHOLD:
            best.outcome = ResolutionOutcome.MERGE
            result.outcome = ResolutionOutcome.MERGE
            result.chosen = best
            audit.append(
                f"MERGE: '{node.title}' → '{best.existing_title}' "
                f"(score: {best.combined_score:.3f})"
            )
        elif best.combined_score < self.CREATE_THRESHOLD:
            result.outcome = ResolutionOutcome.CREATE
            audit.append(
                f"CREATE: best match '{best.existing_title}' "
                f"scored {best.combined_score:.3f} (below {self.CREATE_THRESHOLD})"
            )
        else:
            result.outcome = ResolutionOutcome.DEFER
            result.chosen = best
            audit.append(
                f"DEFER: '{node.title}' ↔ '{best.existing_title}' "
                f"(score: {best.combined_score:.3f}, needs human review)"
            )

        return result

    def _find_exact_matches(self, node: NodeProposal) -> list[dict[str, Any]]:
        """Find nodes with matching title (case-insensitive) and same type."""
        try:
            return self._repo.find_exact_node_matches(
                node.node_type.value, node.title
            )
        except Exception:
            logger.warning("Exact match search failed", exc_info=True)
            return []

    def _find_similar_nodes(self, node: NodeProposal) -> list[dict[str, Any]]:
        """Find embedding-similar nodes via LanceDB."""
        if not self._vector_store or not self._embedding_engine:
            return []

        try:
            text = f"{node.title} {node.content}"
            embedding = self._embedding_engine.embed_text(text)
            results = self._vector_store.dense_search(
                embedding["dense"],
                top_k=5,
                filters={"node_type": node.node_type.value},
            )
            return [r.to_dict() for r in results]
        except Exception:
            logger.warning("Embedding similarity search failed", exc_info=True)
            return []

    def _find_similar_nodes_batch(
        self, nodes: list[NodeProposal]
    ) -> dict[str, list[dict[str, Any]]]:
        """Find embedding-similar nodes for all proposed nodes using batch embedding.

        Returns a dict keyed by temp_id with similar node lists as values.
        """
        if not self._vector_store or not self._embedding_engine or not nodes:
            return {n.temp_id: [] for n in nodes}

        try:
            texts = [f"{n.title} {n.content}" for n in nodes]
            embeddings = self._embedding_engine.embed_batch(texts)

            result: dict[str, list[dict[str, Any]]] = {}
            for node, emb in zip(nodes, embeddings):
                try:
                    search_results = self._vector_store.dense_search(
                        emb["dense"],
                        top_k=5,
                        filters={"node_type": node.node_type.value},
                    )
                    result[node.temp_id] = [r.to_dict() for r in search_results]
                except Exception:
                    result[node.temp_id] = []
            return result
        except Exception:
            logger.warning("Batch embedding similarity search failed", exc_info=True)
            return {n.temp_id: [] for n in nodes}

    def _score_exact_name(
        self,
        candidate: ResolutionCandidate,
        node: NodeProposal,
    ) -> None:
        """Score based on name match — exact, substring, or token overlap."""
        proposed = node.title.lower().strip()
        existing = candidate.existing_title.lower().strip()

        # Exact match
        if proposed == existing:
            candidate.signals["exact_name"] = 1.0
            return

        # One name is a substring of the other (e.g., "Aisha" in "Aisha Nakamura")
        if proposed in existing or existing in proposed:
            # Score by ratio of shorter to longer — "Aisha" (5) / "Aisha Nakamura" (14) = 0.36
            # But we want this to score high enough to matter, so use a floor
            shorter = min(len(proposed), len(existing))
            longer = max(len(proposed), len(existing))
            candidate.signals["exact_name"] = max(0.7, shorter / longer)
            return

        # Token overlap (e.g., "Carlos Rivera" vs "Carlos" shares "carlos")
        proposed_tokens = set(proposed.split())
        existing_tokens = set(existing.split())
        if proposed_tokens and existing_tokens:
            overlap = proposed_tokens & existing_tokens
            if overlap:
                union = proposed_tokens | existing_tokens
                candidate.signals["exact_name"] = 0.6 * len(overlap) / len(union)
                return

        candidate.signals["exact_name"] = 0.0

    def _score_embedding(
        self,
        candidate: ResolutionCandidate,
        similar_nodes: list[dict[str, Any]],
    ) -> None:
        """Score based on embedding cosine similarity."""
        for sim in similar_nodes:
            if sim.get("node_id") == candidate.existing_node_id:
                score = sim.get("score", 0.0)
                if score >= self.EMBEDDING_THRESHOLD:
                    candidate.signals["embedding_similarity"] = score
                else:
                    candidate.signals["embedding_similarity"] = score * 0.5
                return
        candidate.signals["embedding_similarity"] = 0.0

    def _score_network_overlap(
        self,
        candidate: ResolutionCandidate,
        node: NodeProposal,
    ) -> None:
        """Score based on network membership overlap."""
        proposed_networks = set(n.value for n in node.networks)
        existing_networks = set(candidate.existing_networks)

        if not proposed_networks or not existing_networks:
            candidate.signals["same_network"] = 0.0
            return

        overlap = proposed_networks & existing_networks
        if overlap:
            candidate.signals["same_network"] = len(overlap) / max(
                len(proposed_networks), len(existing_networks)
            )
        else:
            candidate.signals["same_network"] = 0.0

    def _score_temporal(
        self,
        candidate: ResolutionCandidate,
        node: NodeProposal,
        created_at: datetime | None = None,
    ) -> None:
        """Score based on temporal proximity (created within 7-day window).

        Args:
            created_at: Pre-fetched created_at for the candidate. When provided,
                        skips the DB query.
        """
        # Check temporal anchor on the proposal
        if node.temporal and node.temporal.occurred_at:
            proposed_time = node.temporal.occurred_at
        else:
            proposed_time = datetime.now(timezone.utc)

        # Use pre-fetched or query DB
        existing_time = created_at
        if existing_time is None:
            try:
                existing_time = self._repo.get_node_created_at(candidate.existing_node_id)
            except Exception:
                pass

        if existing_time:
            # Ensure both are timezone-aware for comparison
            if existing_time.tzinfo is None:
                existing_time = existing_time.replace(tzinfo=timezone.utc)
            if proposed_time.tzinfo is None:
                proposed_time = proposed_time.replace(tzinfo=timezone.utc)
            delta = abs((proposed_time - existing_time).days)
            if delta <= self.TEMPORAL_WINDOW_DAYS:
                candidate.signals["temporal_proximity"] = 1.0 - (delta / self.TEMPORAL_WINDOW_DAYS)
                return

        candidate.signals["temporal_proximity"] = 0.0

    def _score_shared_relationships(
        self,
        candidate: ResolutionCandidate,
        node: NodeProposal,
        proposal: GraphProposal,
        existing_neighbors: set[str] | None = None,
    ) -> None:
        """Score based on shared relationships (connected to same nodes).

        Args:
            existing_neighbors: Pre-fetched neighbor IDs for the candidate.
                                When provided, skips the DB query.
        """
        # Get existing edges for the candidate
        if existing_neighbors is None:
            try:
                existing_edges = self._repo.get_edges(UUID(candidate.existing_node_id))
                existing_neighbors = set()
                for edge in existing_edges:
                    existing_neighbors.add(str(edge.source_id))
                    existing_neighbors.add(str(edge.target_id))
                existing_neighbors.discard(candidate.existing_node_id)
            except Exception:
                candidate.signals["shared_relationships"] = 0.0
                return
        else:
            # Remove self from pre-fetched neighbors
            existing_neighbors = existing_neighbors - {candidate.existing_node_id}

        # Get proposed edges involving this node
        proposed_neighbors = set()
        for edge in proposal.edges_to_create:
            if edge.source_id == node.temp_id:
                proposed_neighbors.add(edge.target_id)
            elif edge.target_id == node.temp_id:
                proposed_neighbors.add(edge.source_id)

        if not existing_neighbors or not proposed_neighbors:
            candidate.signals["shared_relationships"] = 0.0
            return

        # Check for overlap (proposed neighbors that reference existing node IDs)
        overlap = proposed_neighbors & existing_neighbors
        if overlap:
            candidate.signals["shared_relationships"] = min(
                1.0, len(overlap) / len(proposed_neighbors)
            )
        else:
            candidate.signals["shared_relationships"] = 0.0

    def _weighted_sum(self, signals: dict[str, float]) -> float:
        """Compute weighted average of available signals."""
        if not signals:
            return 0.0

        total_weight = sum(self.WEIGHTS[k] for k in signals if k in self.WEIGHTS)
        if total_weight == 0:
            return 0.0

        weighted = sum(
            signals[k] * self.WEIGHTS[k]
            for k in signals
            if k in self.WEIGHTS
        )
        return weighted / total_weight

    def _llm_adjudicate(
        self,
        proposed: NodeProposal,
        candidate: ResolutionCandidate,
    ) -> float:
        """Ask Claude if two nodes refer to the same entity. Returns 0.0-1.0."""
        prompt = (
            f"Are these two entries referring to the same entity?\n\n"
            f"Entry A (proposed):\n"
            f"- Type: {proposed.node_type.value}\n"
            f"- Title: {proposed.title}\n"
            f"- Content: {proposed.content}\n"
            f"- Networks: {[n.value for n in proposed.networks]}\n\n"
            f"Entry B (existing):\n"
            f"- Type: {candidate.existing_node_type}\n"
            f"- Title: {candidate.existing_title}\n"
            f"- Networks: {candidate.existing_networks}\n\n"
            f"Reply with ONLY a number between 0.0 and 1.0 indicating your confidence "
            f"that these refer to the same entity. 1.0 = definitely same, 0.0 = definitely different."
        )

        try:
            response = call_with_retry(
                self._llm_client.responses.create,
                model="gpt-5-nano",
                instructions=(
                    "You are an entity resolution judge. Given two database entries, "
                    "determine if they refer to the same real-world entity. "
                    "Respond with ONLY a single number between 0.0 and 1.0."
                ),
                input=prompt,
                max_output_tokens=50,
            )
            text = response.output_text.strip()
            # Extract float from response
            import re
            match = re.search(r"([01]\.\d+|[01])", text)
            if match:
                return float(match.group(1))
            return 0.5
        except Exception:
            logger.warning("LLM adjudication failed", exc_info=True)
            return 0.5

    def apply_merges(
        self,
        proposal: GraphProposal,
        resolutions: list[ResolutionResult],
    ) -> GraphProposal:
        """Apply MERGE outcomes to the proposal.

        For each MERGE:
        1. Remove the NodeProposal from nodes_to_create
        2. Add a NodeUpdate to nodes_to_update
        3. Rewrite edge source_id/target_id from temp_id to existing UUID
        """
        temp_to_existing: dict[str, str] = {}
        merged_temp_ids: set[str] = set()

        for resolution in resolutions:
            if resolution.outcome == ResolutionOutcome.MERGE and resolution.chosen:
                temp_id = resolution.proposed_temp_id
                existing_id = resolution.chosen.existing_node_id
                temp_to_existing[temp_id] = existing_id
                merged_temp_ids.add(temp_id)

        if not temp_to_existing:
            return proposal

        # Remove merged nodes from nodes_to_create
        remaining_creates = [
            n for n in proposal.nodes_to_create
            if n.temp_id not in merged_temp_ids
        ]

        # Add NodeUpdate entries for merged nodes
        new_updates = list(proposal.nodes_to_update)
        for resolution in resolutions:
            if resolution.outcome == ResolutionOutcome.MERGE and resolution.chosen:
                # Find the original proposal node
                original = next(
                    (n for n in proposal.nodes_to_create if n.temp_id == resolution.proposed_temp_id),
                    None,
                )
                if original:
                    update_data: dict[str, Any] = {}
                    if original.content:
                        update_data["content"] = original.content
                    if original.properties:
                        update_data["properties"] = original.properties
                    if original.networks:
                        update_data["networks"] = [n.value for n in original.networks]

                    if update_data:
                        new_updates.append(NodeUpdate(
                            node_id=resolution.chosen.existing_node_id,
                            updates=update_data,
                            confidence=original.confidence,
                            reason=f"Merged from proposed node '{original.title}'",
                        ))

        # Rewrite edge references
        new_edges = []
        for edge in proposal.edges_to_create:
            source = temp_to_existing.get(edge.source_id, edge.source_id)
            target = temp_to_existing.get(edge.target_id, edge.target_id)
            new_edges.append(edge.model_copy(update={
                "source_id": source,
                "target_id": target,
            }))

        return proposal.model_copy(update={
            "nodes_to_create": remaining_creates,
            "nodes_to_update": new_updates,
            "edges_to_create": new_edges,
        })
