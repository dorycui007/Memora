"""Election intelligence — candidate landscape, voter blocs, and endorsement analysis.

Analyzes ELECTION nodes and their relationships to provide strategic
intelligence for campus governance and organizational elections.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ElectionIntel:
    """Analyzes elections with candidate and endorsement intelligence."""

    def __init__(self, repo) -> None:
        self._repo = repo

    def get_elections(self) -> list[dict[str, Any]]:
        """Get all elections with enriched intelligence."""
        from memora.graph.models import NodeFilter, NodeType, parse_properties

        filters = NodeFilter(node_types=[NodeType.ELECTION], limit=100)
        elections = self._repo.query_nodes(filters)

        results = []
        for e in elections:
            props = parse_properties(e.properties)
            intel = self._analyze_election(str(e.id))
            results.append({
                "id": str(e.id),
                "title": e.title,
                "position_title": props.get("position_title", ""),
                "organization": props.get("organization", ""),
                "date": props.get("date"),
                "candidates": props.get("candidates", []),
                "result": props.get("result", "pending"),
                "vote_count": props.get("vote_count"),
                "networks": [n.value for n in e.networks],
                **intel,
            })

        return results

    def _analyze_election(self, election_id: str) -> dict[str, Any]:
        """Analyze an election's candidate and endorsement landscape."""
        edges = self._repo.get_edges(election_id, "incoming")

        candidates = []
        endorsements = []

        for e in edges:
            et = e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)
            source = self._repo.get_node(str(e.source_id))
            if not source:
                continue

            if et == "CANDIDATE_IN":
                from memora.graph.models import parse_properties
                props = parse_properties(source.properties)
                candidates.append({
                    "id": str(source.id),
                    "name": props.get("name", source.title),
                    "organization": props.get("organization", ""),
                })
            elif et == "ENDORSES":
                endorsements.append({
                    "endorser_id": str(source.id),
                    "endorser_name": source.title,
                })

        return {
            "candidate_count": len(candidates),
            "candidates_detail": candidates,
            "endorsement_count": len(endorsements),
            "endorsements": endorsements,
        }

    def get_endorsement_graph(self, election_id: str) -> dict[str, Any]:
        """Get the endorsement network for an election."""
        election = self._repo.get_node(election_id)
        if not election:
            return {"nodes": [], "edges": []}

        edges = self._repo.get_edges(election_id, "incoming")
        nodes = [{"id": election_id, "title": election.title, "type": "ELECTION"}]
        graph_edges = []

        for e in edges:
            source = self._repo.get_node(str(e.source_id))
            if source:
                ntype = source.node_type.value if hasattr(source.node_type, "value") else str(source.node_type)
                nodes.append({
                    "id": str(source.id),
                    "title": source.title,
                    "type": ntype,
                })
                et = e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type)
                graph_edges.append({
                    "from": str(e.source_id),
                    "to": election_id,
                    "type": et,
                })

        return {"nodes": nodes, "edges": graph_edges}
