"""Relationship Decay — detect neglected relationships based on interaction recency."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)

# Default interaction-gap thresholds (days) per relationship tier
DEFAULT_THRESHOLDS: dict[str, int] = {
    "close": 7,
    "regular": 14,
    "acquaintance": 30,
}


class RelationshipDecayDetector:
    """Detect relationships that are at risk of decay due to neglect."""

    def __init__(self, repo: GraphRepository) -> None:
        self._repo = repo
        self._thresholds = dict(DEFAULT_THRESHOLDS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> list[dict[str, Any]]:
        """Scan all PERSON nodes and return those exceeding their decay threshold.

        Each result dict contains: person_name, days_since_interaction,
        relationship_type, threshold, node_id, outstanding_commitments.
        """
        persons = self._get_person_nodes()
        now = datetime.now(timezone.utc)
        decaying: list[dict[str, Any]] = []

        for p in persons:
            props = p.get("properties") or {}
            rel_type = self._classify_relationship(props)
            threshold = self._thresholds.get(rel_type, DEFAULT_THRESHOLDS["acquaintance"])

            last_interaction = self._parse_datetime(props.get("last_interaction"))
            if last_interaction is None:
                # Also try the node-level last_accessed
                last_interaction = self._parse_datetime(p.get("last_accessed"))
            if last_interaction is None:
                # No interaction data — skip rather than false-flag
                continue

            days_since = (now - last_interaction).days
            if days_since >= threshold:
                outstanding = self._get_outstanding_commitments(p["id"])
                decaying.append({
                    "node_id": p["id"],
                    "person_name": p.get("title", "Unknown"),
                    "days_since_interaction": days_since,
                    "relationship_type": rel_type,
                    "threshold": threshold,
                    "outstanding_commitments": outstanding,
                })

        logger.info("Relationship decay scan found %d decaying relationships", len(decaying))
        return decaying

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_person_nodes(self) -> list[dict[str, Any]]:
        """Query all PERSON nodes from the graph."""
        try:
            rows = self._repo._conn.execute(
                """SELECT id, title, properties, last_accessed, networks
                   FROM nodes
                   WHERE deleted = FALSE AND node_type = 'PERSON'"""
            ).fetchall()
        except Exception:
            logger.warning("Failed to fetch person nodes", exc_info=True)
            return []

        cols = ["id", "title", "properties", "last_accessed", "networks"]
        results: list[dict[str, Any]] = []
        for row in rows:
            d = dict(zip(cols, row))
            if isinstance(d["properties"], str):
                try:
                    d["properties"] = json.loads(d["properties"])
                except (json.JSONDecodeError, TypeError):
                    d["properties"] = {}
            results.append(d)
        return results

    def _classify_relationship(self, properties: dict[str, Any]) -> str:
        """Classify a person's relationship tier based on *relationship_to_user*.

        Returns one of: 'close', 'regular', 'acquaintance'.
        """
        rel = str(properties.get("relationship_to_user", "")).lower()
        close_keywords = {
            "partner", "spouse", "parent", "sibling", "child",
            "best friend", "close friend", "family",
        }
        regular_keywords = {
            "friend", "colleague", "teammate", "mentor", "mentee",
            "manager", "coworker", "collaborator",
        }
        for kw in close_keywords:
            if kw in rel:
                return "close"
        for kw in regular_keywords:
            if kw in rel:
                return "regular"
        return "acquaintance"

    def _get_outstanding_commitments(self, person_node_id: str) -> list[dict[str, Any]]:
        """Return open commitments connected to the given person node."""
        try:
            rows = self._repo._conn.execute(
                """SELECT n.id, n.title, n.properties
                   FROM nodes n
                   JOIN edges e ON (
                       (e.source_id = ? AND e.target_id = n.id)
                       OR (e.target_id = ? AND e.source_id = n.id)
                   )
                   WHERE n.deleted = FALSE
                     AND n.node_type = 'COMMITMENT'
                     AND json_extract_string(n.properties, '$.status') = 'open'""",
                [person_node_id, person_node_id],
            ).fetchall()
        except Exception:
            logger.warning(
                "Failed to fetch commitments for person %s", person_node_id
            )
            return []

        results: list[dict[str, Any]] = []
        for row in rows:
            props = row[2]
            if isinstance(props, str):
                try:
                    props = json.loads(props)
                except (json.JSONDecodeError, TypeError):
                    props = {}
            results.append({
                "node_id": row[0],
                "title": row[1],
                "due_date": props.get("due_date"),
            })
        return results

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """Safely parse a datetime from a string or datetime."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None
