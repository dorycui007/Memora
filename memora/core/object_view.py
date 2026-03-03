"""Entity 360 Object View — unified intelligence hub for any entity.

Transforms the dossier from a lookup tool into Palantir's Object View —
the central intelligence hub for any entity. Pulls together data from
graph algorithms and connectors into a unified view.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from memora.graph.models import enum_val

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """A ranked connection to another entity."""

    node_id: str
    title: str
    node_type: str
    edge_type: str
    direction: str  # "outgoing" or "incoming"
    strength: float
    weight: float
    confidence: float


@dataclass
class TimelineEvent:
    """A chronological activity involving the entity."""

    node_id: str
    title: str
    node_type: str
    edge_type: str
    date: str
    created_at: str


@dataclass
class ObjectView:
    """Complete 360-degree intelligence view of an entity."""

    entity: Any  # BaseNode
    connections: list[ConnectionInfo] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    patterns: list[dict] = field(default_factory=list)
    outcomes: list[dict] = field(default_factory=list)
    bridges: list[dict] = field(default_factory=list)
    centrality_rank: int | None = None
    communities: list[int] = field(default_factory=list)
    predicted_links: list[dict] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    subgraph_nodes: int = 0
    subgraph_edges: int = 0
    degree: int = 0
    pagerank_score: float = 0.0


class ObjectViewBuilder:
    """Hydrates the full ObjectView for an entity.

    Pulls data from the graph repository, truth layer, graph algorithms,
    and connector metadata to produce a comprehensive entity view.
    """

    def __init__(self, repo, algorithms=None) -> None:
        self.repo = repo
        self.algorithms = algorithms

    def build(
        self,
        entity,
        neighborhood_hops: int = 2,
        include_graph_intel: bool = True,
        facts_limit: int = 20,
        patterns_limit: int = 10,
        outcomes_limit: int = 10,
        bridges_limit: int = 10,
        predictions_limit: int = 5,
    ) -> ObjectView:
        """Build a complete ObjectView for the given entity.

        Args:
            entity: The BaseNode entity to build the view for.
            neighborhood_hops: Number of hops for neighborhood traversal.
            include_graph_intel: Whether to compute graph algorithm metrics.
            facts_limit: Maximum number of facts to include.
            patterns_limit: Maximum number of patterns to include.
            outcomes_limit: Maximum number of outcomes to include.
            bridges_limit: Maximum number of bridges to include.
            predictions_limit: Maximum number of predicted links to include.

        Returns:
            A fully hydrated ObjectView.
        """
        entity_str = str(entity.id)

        view = ObjectView(entity=entity)

        # 1. Neighborhood & connections
        subgraph = self.repo.get_neighborhood(entity.id, hops=neighborhood_hops)
        view.subgraph_nodes = len(subgraph.nodes)
        view.subgraph_edges = len(subgraph.edges)

        nodes_by_id = {str(n.id): n for n in subgraph.nodes}
        view.connections = self._compute_connections(entity_str, subgraph, nodes_by_id)
        view.degree = len(view.connections)

        # 2. Timeline
        view.timeline = self._build_timeline(entity_str)

        # 3. Facts
        view.facts = self._get_facts(entity_str, facts_limit)

        # 4. Patterns
        view.patterns = self._get_patterns(entity_str, patterns_limit)

        # 5. Outcomes
        view.outcomes = self._get_outcomes(entity_str, outcomes_limit)

        # 6. Bridges
        view.bridges = self._get_bridges(entity_str, bridges_limit)

        # 7. Graph intelligence (if algorithms available)
        if include_graph_intel and self.algorithms:
            self._add_graph_intel(view, entity_str, predictions_limit)

        # 8. Data sources
        view.data_sources = self._collect_data_sources(entity, subgraph)

        return view

    def _compute_connections(
        self, entity_str: str, subgraph, nodes_by_id: dict
    ) -> list[ConnectionInfo]:
        """Compute and rank connections by strength."""
        direct_edges = [
            e for e in subgraph.edges
            if str(e.source_id) == entity_str or str(e.target_id) == entity_str
        ]

        connections = []
        for edge in direct_edges:
            src, tgt = str(edge.source_id), str(edge.target_id)
            neighbor_id = tgt if src == entity_str else src
            direction = "outgoing" if src == entity_str else "incoming"
            neighbor = nodes_by_id.get(neighbor_id)
            if not neighbor:
                continue

            etype = enum_val(edge.edge_type)
            ntype = enum_val(neighbor.node_type)

            strength = (
                edge.weight * 0.4
                + edge.confidence * 0.3
                + neighbor.confidence * 0.2
                + (neighbor.decay_score or 0.5) * 0.1
            )

            connections.append(ConnectionInfo(
                node_id=neighbor_id,
                title=neighbor.title,
                node_type=ntype,
                edge_type=etype,
                direction=direction,
                strength=strength,
                weight=edge.weight,
                confidence=edge.confidence,
            ))

        connections.sort(key=lambda c: c.strength, reverse=True)
        return connections

    def _build_timeline(self, entity_str: str) -> list[TimelineEvent]:
        """Build chronological timeline for the entity."""
        try:
            temporal = self.repo.get_temporal_neighbors(entity_str)
            return [
                TimelineEvent(
                    node_id=item.get("node_id", ""),
                    title=item.get("title", "unknown"),
                    node_type=item.get("node_type", ""),
                    edge_type=item.get("edge_type", ""),
                    date=str(item.get("created_at", ""))[:10],
                    created_at=str(item.get("created_at", "")),
                )
                for item in temporal
            ]
        except Exception:
            return []

    def _get_facts(self, entity_str: str, limit: int) -> list[dict]:
        """Get verified facts for the entity."""
        try:
            from memora.core.truth_layer import TruthLayer
            truth = TruthLayer(conn=self.repo.get_truth_layer_conn())
            return truth.query_facts(node_id=entity_str, status="active", limit=limit)
        except Exception:
            return []

    def _get_patterns(self, entity_str: str, limit: int) -> list[dict]:
        """Get detected patterns for the entity."""
        try:
            return self.repo.get_patterns_for_node(entity_str, limit=limit)
        except Exception:
            return []

    def _get_outcomes(self, entity_str: str, limit: int) -> list[dict]:
        """Get recorded outcomes for the entity."""
        try:
            outcomes = self.repo.get_outcomes_for_node(entity_str)
            return outcomes[:limit]
        except Exception:
            return []

    def _get_bridges(self, entity_str: str, limit: int) -> list[dict]:
        """Get cross-network bridges for the entity."""
        try:
            return self.repo.get_bridges_for_nodes([entity_str], limit=limit)
        except Exception:
            return []

    def _add_graph_intel(self, view: ObjectView, entity_str: str, predictions_limit: int):
        """Add graph algorithm metrics to the view."""
        try:
            view.centrality_rank = self.algorithms.get_entity_centrality_rank(entity_str)
        except Exception:
            logger.debug("Failed to get centrality rank", exc_info=True)

        try:
            view.communities = self.algorithms.get_entity_communities(entity_str)
        except Exception:
            logger.debug("Failed to get communities", exc_info=True)

        try:
            view.predicted_links = self.algorithms.get_entity_predicted_links(
                entity_str, top_k=predictions_limit
            )
        except Exception:
            logger.debug("Failed to get predicted links", exc_info=True)

        try:
            pr = self.algorithms.pagerank()
            for entry in pr:
                if entry["node_id"] == entity_str:
                    view.pagerank_score = entry["pagerank"]
                    break
        except Exception:
            pass

    def _collect_data_sources(self, entity, subgraph) -> list[str]:
        """Collect data source information for the entity."""
        sources = set()

        # Check capture source
        if entity.source_capture_id:
            try:
                capture = self.repo.get_capture(entity.source_capture_id)
                if capture and capture.metadata:
                    source = capture.metadata.get("source", "")
                    if source:
                        sources.add(source)
                    connector = capture.metadata.get("connector_name", "")
                    if connector:
                        sources.add(f"connector:{connector}")
                if capture:
                    sources.add("capture")
            except Exception:
                pass

        # Check connected nodes for their sources
        for node in subgraph.nodes:
            if node.source_capture_id:
                try:
                    capture = self.repo.get_capture(node.source_capture_id)
                    if capture and capture.metadata:
                        source = capture.metadata.get("source", "")
                        if source and source not in ("", "capture"):
                            sources.add(source)
                except Exception:
                    pass

        if not sources:
            sources.add("manual_capture")

        return sorted(sources)


def compare_entities(builder: ObjectViewBuilder, entity_a, entity_b) -> dict:
    """Side-by-side comparison of two entities.

    Returns dict with both views and comparison metrics.
    """
    view_a = builder.build(entity_a)
    view_b = builder.build(entity_b)

    # Compute overlap
    a_connections = {c.node_id for c in view_a.connections}
    b_connections = {c.node_id for c in view_b.connections}
    shared_connections = a_connections & b_connections

    a_communities = set(view_a.communities)
    b_communities = set(view_b.communities)
    shared_communities = a_communities & b_communities

    return {
        "entity_a": view_a,
        "entity_b": view_b,
        "shared_connections": len(shared_connections),
        "shared_connection_ids": list(shared_connections),
        "shared_communities": list(shared_communities),
        "a_unique_connections": len(a_connections - b_connections),
        "b_unique_connections": len(b_connections - a_connections),
        "rank_difference": (
            abs((view_a.centrality_rank or 0) - (view_b.centrality_rank or 0))
            if view_a.centrality_rank and view_b.centrality_rank
            else None
        ),
    }
