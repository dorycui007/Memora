"""Strategic position tracking — aggregation, health scoring, and blocker analysis.

Tracks positions (roles, offices) the user holds or is pursuing,
with commitment tracking and cross-position flywheel detection.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PositionTracker:
    """Tracks strategic positions with health metrics and blocker analysis."""

    def __init__(self, repo) -> None:
        self._repo = repo

    def get_all_positions(self) -> list[dict[str, Any]]:
        """Get all POSITION nodes with enriched metrics."""
        from memora.graph.models import NodeFilter, NodeType, parse_properties

        filters = NodeFilter(node_types=[NodeType.POSITION], limit=50)
        positions = self._repo.query_nodes(filters)

        results = []
        for pos in positions:
            props = parse_properties(pos.properties)
            metrics = self._compute_position_metrics(str(pos.id))
            results.append({
                "id": str(pos.id),
                "title": pos.title,
                "organization": props.get("organization", ""),
                "status": props.get("status", ""),
                "holder": props.get("holder", ""),
                "time_hrs_week": props.get("time_hrs_week"),
                "start_date": props.get("start_date"),
                "end_date": props.get("end_date"),
                "blockers": props.get("blockers", []),
                "networks": [n.value for n in pos.networks],
                "decay_score": pos.decay_score,
                **metrics,
            })

        return results

    def _compute_position_metrics(self, position_id: str) -> dict[str, Any]:
        """Compute health metrics for a position."""
        all_edges = self._repo.get_edges(position_id)

        commitment_count = 0
        completed_commitments = 0
        overdue_commitments = 0
        goal_count = 0
        people_count = 0

        from memora.graph.models import parse_properties

        for e in all_edges:
            other_id = str(e.source_id) if str(e.target_id) == position_id else str(e.target_id)
            other = self._repo.get_node(other_id)
            if not other:
                continue

            ntype = other.node_type.value if hasattr(other.node_type, "value") else str(other.node_type)

            if ntype == "COMMITMENT":
                commitment_count += 1
                props = parse_properties(other.properties)
                status = props.get("status", "open")
                if status == "completed":
                    completed_commitments += 1
                elif status == "overdue":
                    overdue_commitments += 1
            elif ntype == "GOAL":
                goal_count += 1
            elif ntype == "PERSON":
                people_count += 1

        completion_rate = (
            completed_commitments / commitment_count if commitment_count > 0 else 0.0
        )

        # Health score: weighted combination
        health = 1.0
        if overdue_commitments > 0:
            health -= min(0.4, overdue_commitments * 0.1)
        if commitment_count > 0:
            health *= (0.5 + 0.5 * completion_rate)
        health = max(0.0, min(1.0, health))

        return {
            "health": round(health, 2),
            "commitment_count": commitment_count,
            "completed_commitments": completed_commitments,
            "overdue_commitments": overdue_commitments,
            "goal_count": goal_count,
            "people_count": people_count,
            "completion_rate": round(completion_rate, 2),
        }

    def get_position_detail(self, position_id: str) -> dict[str, Any] | None:
        """Get detailed view of a single position."""
        node = self._repo.get_node(position_id)
        if not node:
            return None

        from memora.graph.models import parse_properties

        props = parse_properties(node.properties)
        metrics = self._compute_position_metrics(position_id)

        # Get related entities
        edges = self._repo.get_edges(position_id)

        commitments = []
        goals = []
        people = []

        for e in edges:
            other_id = str(e.source_id) if str(e.target_id) == position_id else str(e.target_id)
            other = self._repo.get_node(other_id)
            if not other:
                continue

            ntype = other.node_type.value if hasattr(other.node_type, "value") else str(other.node_type)
            other_props = parse_properties(other.properties)

            if ntype == "COMMITMENT":
                commitments.append({
                    "id": str(other.id),
                    "title": other.title,
                    "status": other_props.get("status", "open"),
                    "due_date": other_props.get("due_date"),
                    "priority": other_props.get("priority", "medium"),
                })
            elif ntype == "GOAL":
                goals.append({
                    "id": str(other.id),
                    "title": other.title,
                    "status": other_props.get("status", "active"),
                    "progress": other_props.get("progress", 0.0),
                })
            elif ntype == "PERSON":
                people.append({
                    "id": str(other.id),
                    "title": other.title,
                    "name": other_props.get("name", other.title),
                    "role": other_props.get("role", ""),
                })

        return {
            "id": str(node.id),
            "title": node.title,
            "properties": props,
            "metrics": metrics,
            "commitments": commitments,
            "goals": goals,
            "people": people,
        }

    def detect_flywheels(self) -> list[dict[str, Any]]:
        """Detect cross-position flywheel reinforcement patterns.

        A flywheel exists when activity in one position strengthens another
        through shared people, organizations, or bridging entities.
        """
        positions = self.get_all_positions()
        flywheels = []

        # Check pairwise position connections via shared entities
        for i, p1 in enumerate(positions):
            for p2 in positions[i + 1:]:
                shared = self._find_shared_connections(p1["id"], p2["id"])
                if shared:
                    flywheels.append({
                        "position_a": p1["title"],
                        "position_b": p2["title"],
                        "shared_entities": len(shared),
                        "bridge_type": "shared_connections",
                    })

        return flywheels

    def _find_shared_connections(self, pos_a_id: str, pos_b_id: str) -> list[str]:
        """Find entities connected to both positions."""
        edges_a = self._repo.get_edges(pos_a_id)
        edges_b = self._repo.get_edges(pos_b_id)

        neighbors_a = set()
        for e in edges_a:
            neighbors_a.add(str(e.source_id))
            neighbors_a.add(str(e.target_id))
        neighbors_a.discard(pos_a_id)

        neighbors_b = set()
        for e in edges_b:
            neighbors_b.add(str(e.source_id))
            neighbors_b.add(str(e.target_id))
        neighbors_b.discard(pos_b_id)

        return list(neighbors_a & neighbors_b)
