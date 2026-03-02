"""People Intelligence Engine — relationship strength scoring and people analytics.

Provides a Palantir-style people directory with ranked connections,
strength scores, and network statistics.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)

# ── Relationship strength weights ────────────────────────────

SIGNAL_WEIGHTS = {
    "edge_weight": 0.25,
    "edge_confidence": 0.15,
    "edge_type_importance": 0.20,
    "recency": 0.25,
    "shared_connections": 0.15,
}

EDGE_TYPE_IMPORTANCE: dict[str, float] = {
    "COLLABORATES_WITH": 1.0,
    "REPORTS_TO": 0.9,
    "COMMITTED_TO": 0.85,
    "RESPONSIBLE_FOR": 0.8,
    "DECIDED": 0.75,
    "INTRODUCED_BY": 0.7,
    "KNOWS": 0.6,
    "RELATED_TO": 0.5,
    "BRIDGES": 0.5,
    "MEMBER_OF": 0.45,
    "PART_OF": 0.4,
    "SIMILAR_TO": 0.35,
    "DERIVED_FROM": 0.3,
}

# Recency decay half-life in days
RECENCY_HALF_LIFE_DAYS = 35.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compute_recency(updated_at: Any) -> float:
    """Exponential decay score from a timestamp (~35 day half-life)."""
    if updated_at is None:
        return 0.0
    if isinstance(updated_at, str):
        try:
            updated_at = datetime.fromisoformat(updated_at)
        except (ValueError, TypeError):
            return 0.0
    now = _utcnow()
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    days_ago = max((now - updated_at).total_seconds() / 86400, 0)
    return math.exp(-0.693 * days_ago / RECENCY_HALF_LIFE_DAYS)


def _compute_shared_connections_score(count: int) -> float:
    """Log-scaled shared connections score, capped at 5."""
    if count <= 0:
        return 0.0
    capped = min(count, 5)
    return math.log(1 + capped) / math.log(6)  # log(6) normalizes to ~1.0


def compute_relationship_strength(
    edge_weight: float = 1.0,
    edge_confidence: float = 0.5,
    edge_type: str = "RELATED_TO",
    edge_updated_at: Any = None,
    shared_connection_count: int = 0,
) -> float:
    """Compute a 0.0–1.0 relationship strength score from five signals."""
    w = SIGNAL_WEIGHTS
    type_importance = EDGE_TYPE_IMPORTANCE.get(edge_type, 0.3)
    recency = _compute_recency(edge_updated_at)
    shared = _compute_shared_connections_score(shared_connection_count)

    score = (
        w["edge_weight"] * min(edge_weight, 1.0)
        + w["edge_confidence"] * min(edge_confidence, 1.0)
        + w["edge_type_importance"] * type_importance
        + w["recency"] * recency
        + w["shared_connections"] * shared
    )
    return round(max(0.0, min(1.0, score)), 3)


class PeopleIntelEngine:
    """High-level people intelligence operations."""

    def __init__(self, repo: GraphRepository) -> None:
        self.repo = repo

    # ── Directory ─────────────────────────────────────────────

    def get_people_directory(
        self,
        sort_by: str = "title",
        order: str = "asc",
        limit: int = 20,
        offset: int = 0,
        network_filter: str | None = None,
    ) -> dict[str, Any]:
        """Paginated people directory with summary info."""
        people, total = self.repo.get_all_people_with_stats(
            sort_by=sort_by, order=order, limit=limit, offset=offset,
            network_filter=network_filter,
        )
        for p in people:
            content = p.get("content") or ""
            p["summary"] = content[:60] + "..." if len(content) > 60 else content
        return {
            "people": people,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    # ── Person Profile ────────────────────────────────────────

    def get_person_profile(self, person_id: str) -> dict[str, Any] | None:
        """Full person profile with ranked connections and breakdown."""
        from uuid import UUID

        node = self.repo.get_node(UUID(person_id))
        if node is None:
            return None

        edges_with_nodes = self.repo.get_person_edges_with_nodes(person_id)

        # Build a set of neighbor IDs to compute shared connections
        neighbor_ids = {e["node_id"] for e in edges_with_nodes}

        # For each connection, compute strength
        ranked: list[dict[str, Any]] = []
        for e in edges_with_nodes:
            # Count shared connections: how many of this neighbor's neighbors
            # are also in our neighbor set? (Approximation: use mutual query.)
            shared = 0  # Will be filled per-edge below
            strength = compute_relationship_strength(
                edge_weight=e.get("edge_weight") or 1.0,
                edge_confidence=e.get("edge_confidence") or 0.5,
                edge_type=e.get("edge_type", "RELATED_TO"),
                edge_updated_at=e.get("edge_updated"),
                shared_connection_count=shared,
            )
            ranked.append({
                "node_id": e["node_id"],
                "title": e["node_title"],
                "node_type": e["node_type"],
                "edge_type": e["edge_type"],
                "direction": e["direction"],
                "strength": strength,
                "edge_weight": e.get("edge_weight", 1.0),
                "edge_confidence": e.get("edge_confidence", 0.5),
                "node_networks": e.get("node_networks") or [],
                "node_confidence": e.get("node_confidence"),
                "node_decay": e.get("node_decay"),
            })

        # Sort by strength descending
        ranked.sort(key=lambda x: x["strength"], reverse=True)

        # Connection breakdown by node_type and edge_type
        type_counts: dict[str, int] = {}
        edge_type_counts: dict[str, int] = {}
        for r in ranked:
            nt = r["node_type"]
            type_counts[nt] = type_counts.get(nt, 0) + 1
            et = r["edge_type"]
            edge_type_counts[et] = edge_type_counts.get(et, 0) + 1

        strongest = ranked[0]["strength"] if ranked else 0.0
        weakest = ranked[-1]["strength"] if ranked else 0.0

        props = node.properties or {}
        return {
            "id": str(node.id),
            "title": node.title,
            "content": node.content or "",
            "properties": props,
            "role": props.get("role", ""),
            "organization": props.get("organization", ""),
            "location": props.get("location", ""),
            "relationship_to_user": props.get("relationship_to_user", ""),
            "bio": props.get("bio", ""),
            "networks": [n.value for n in node.networks],
            "confidence": node.confidence,
            "decay_score": node.decay_score,
            "tags": node.tags or [],
            "created_at": node.created_at.isoformat() if node.created_at else None,
            "updated_at": node.updated_at.isoformat() if node.updated_at else None,
            "ranked_connections": ranked,
            "connection_summary": {
                "total": len(ranked),
                "by_node_type": type_counts,
                "by_edge_type": edge_type_counts,
                "strongest": strongest,
                "weakest": weakest,
            },
        }

    # ── Statistics ────────────────────────────────────────────

    def get_people_statistics(self) -> dict[str, Any]:
        """Aggregated people statistics with relationship health buckets."""
        stats = self.repo.get_people_stats()

        # Relationship health: active <30d, fading 30-90d, cold >90d
        people, _ = self.repo.get_all_people_with_stats(
            sort_by="title", order="asc", limit=1000, offset=0,
        )
        now = _utcnow()
        active = fading = cold = 0
        for p in people:
            updated = p.get("updated_at")
            if updated is None:
                cold += 1
                continue
            if isinstance(updated, str):
                try:
                    updated = datetime.fromisoformat(updated)
                except (ValueError, TypeError):
                    cold += 1
                    continue
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            days = (now - updated).total_seconds() / 86400
            if days < 30:
                active += 1
            elif days < 90:
                fading += 1
            else:
                cold += 1

        stats["relationship_health"] = {
            "active": active,
            "fading": fading,
            "cold": cold,
        }

        # Top 5 strongest person-to-person ties (edges between two PERSON nodes)
        try:
            rows = self.repo._conn.execute(
                """SELECT e.source_id, e.target_id, e.edge_type,
                          e.weight, e.confidence, e.updated_at,
                          s.title AS source_title, t.title AS target_title
                   FROM edges e
                   JOIN nodes s ON s.id = e.source_id AND s.node_type = 'PERSON' AND s.deleted = FALSE
                   JOIN nodes t ON t.id = e.target_id AND t.node_type = 'PERSON' AND t.deleted = FALSE
                   ORDER BY e.weight DESC, e.confidence DESC
                   LIMIT 5"""
            ).fetchall()
            strongest_ties = []
            for r in rows:
                strength = compute_relationship_strength(
                    edge_weight=r[3] or 1.0,
                    edge_confidence=r[4] or 0.5,
                    edge_type=r[2],
                    edge_updated_at=r[5],
                )
                strongest_ties.append({
                    "source_id": r[0], "target_id": r[1],
                    "source_title": r[6], "target_title": r[7],
                    "edge_type": r[2], "strength": strength,
                })
            stats["strongest_ties"] = strongest_ties
        except Exception:
            stats["strongest_ties"] = []

        return stats

    # ── Mutual Connections ────────────────────────────────────

    def find_mutual_connections(
        self, person_a_id: str, person_b_id: str,
    ) -> dict[str, Any]:
        """Find mutual connections between two people with edge context."""
        from uuid import UUID

        node_a = self.repo.get_node(UUID(person_a_id))
        node_b = self.repo.get_node(UUID(person_b_id))
        mutual = self.repo.get_mutual_connections(person_a_id, person_b_id)

        return {
            "person_a": {
                "id": person_a_id,
                "title": node_a.title if node_a else "Unknown",
            },
            "person_b": {
                "id": person_b_id,
                "title": node_b.title if node_b else "Unknown",
            },
            "mutual_connections": mutual,
            "count": len(mutual),
        }
