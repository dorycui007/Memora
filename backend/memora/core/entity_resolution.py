"""Entity Resolution — multi-signal deduplication and merge engine.

Resolves proposed nodes against existing graph nodes using 6 weighted signals:
exact name match, embedding similarity, network overlap, temporal proximity,
shared relationships, and optional LLM adjudication.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
        """Resolve all proposed nodes against the existing graph."""
        results = []
        for node_proposal in proposal.nodes_to_create:
            result = self._resolve_single(node_proposal, proposal)
            results.append(result)
        return results

    def _resolve_single(
        self,
        node: NodeProposal,
        proposal: GraphProposal,
    ) -> ResolutionResult:
        """Resolve a single proposed node."""
        result = ResolutionResult(
            proposed_temp_id=node.temp_id,
            proposed_title=node.title,
        )
        audit = result.audit_log

        # 1. Find exact name matches in DB
        exact_matches = self._find_exact_matches(node)
        audit.append(f"Exact name search: {len(exact_matches)} matches for '{node.title}'")

        # 2. Find embedding-similar nodes
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
        if not candidates:
            result.outcome = ResolutionOutcome.CREATE
            audit.append("No candidates found — creating new node")
            return result

        # 4. Score each candidate across all non-LLM signals
        for candidate in candidates:
            self._score_exact_name(candidate, node)
            self._score_embedding(candidate, similar_nodes)
            self._score_network_overlap(candidate, node)
            self._score_temporal(candidate, node)
            self._score_shared_relationships(candidate, node, proposal)
            candidate.combined_score = self._weighted_sum(candidate.signals)

        # 5. LLM adjudication for ambiguous cases
        for candidate in candidates:
            if self.CREATE_THRESHOLD <= candidate.combined_score < self.MERGE_THRESHOLD:
                if self._llm_client:
                    llm_score = self._llm_adjudicate(node, candidate)
                    candidate.signals["llm_adjudication"] = llm_score
                    candidate.combined_score = self._weighted_sum(candidate.signals)
                    audit.append(
                        f"LLM adjudication for '{candidate.existing_title}': {llm_score:.2f}"
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
            rows = self._repo._conn.execute(
                """SELECT id, node_type, title, networks, created_at
                   FROM nodes
                   WHERE deleted = FALSE
                   AND node_type = ?
                   AND LOWER(title) = LOWER(?)""",
                [node.node_type.value, node.title],
            ).fetchall()

            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "node_type": row[1],
                    "title": row[2],
                    "networks": row[3] if row[3] else [],
                    "created_at": row[4],
                })
            return results
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

    def _score_exact_name(
        self,
        candidate: ResolutionCandidate,
        node: NodeProposal,
    ) -> None:
        """Score based on exact name match."""
        if candidate.existing_title.lower().strip() == node.title.lower().strip():
            candidate.signals["exact_name"] = 1.0
        else:
            # Partial match
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
    ) -> None:
        """Score based on temporal proximity (created within 7-day window)."""
        # Check temporal anchor on the proposal
        if node.temporal and node.temporal.occurred_at:
            proposed_time = node.temporal.occurred_at
        else:
            proposed_time = datetime.utcnow()

        # Get creation date of existing node
        try:
            row = self._repo._conn.execute(
                "SELECT created_at FROM nodes WHERE id = ?",
                [candidate.existing_node_id],
            ).fetchone()
            if row and row[0]:
                if isinstance(row[0], str):
                    existing_time = datetime.fromisoformat(row[0])
                else:
                    existing_time = row[0]
                delta = abs((proposed_time - existing_time).days)
                if delta <= self.TEMPORAL_WINDOW_DAYS:
                    candidate.signals["temporal_proximity"] = 1.0 - (delta / self.TEMPORAL_WINDOW_DAYS)
                    return
        except Exception:
            pass

        candidate.signals["temporal_proximity"] = 0.0

    def _score_shared_relationships(
        self,
        candidate: ResolutionCandidate,
        node: NodeProposal,
        proposal: GraphProposal,
    ) -> None:
        """Score based on shared relationships (connected to same nodes)."""
        # Get existing edges for the candidate
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
