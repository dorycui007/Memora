"""Gap Detection — identify orphans, stalled goals, dead-end projects, and knowledge gaps."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)


class GapDetector:
    """Detect structural and temporal gaps in the knowledge graph."""

    def __init__(self, repo: GraphRepository) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_all(self) -> dict[str, Any]:
        """Run all gap-detection heuristics.

        Returns a dict with keys: orphaned_nodes, stalled_goals,
        dead_end_projects, isolated_concepts, unresolved_decisions.
        """
        results: dict[str, Any] = {
            "orphaned_nodes": self._find_orphaned_nodes(),
            "stalled_goals": self._find_stalled_goals(),
            "dead_end_projects": self._find_dead_end_projects(),
            "isolated_concepts": self._find_isolated_concepts(),
            "unresolved_decisions": self._find_unresolved_decisions(),
        }

        total = sum(len(v) for v in results.values())
        logger.info("Gap detection found %d total issues", total)
        return results

    # ------------------------------------------------------------------
    # Detection methods
    # ------------------------------------------------------------------

    def _find_orphaned_nodes(self) -> list[dict[str, Any]]:
        """Find nodes with zero edges (neither source nor target)."""
        try:
            rows = self._repo._conn.execute(
                """SELECT n.id, n.node_type, n.title, n.created_at
                   FROM nodes n
                   LEFT JOIN edges e_src ON e_src.source_id = n.id
                   LEFT JOIN edges e_tgt ON e_tgt.target_id = n.id
                   WHERE n.deleted = FALSE
                     AND e_src.id IS NULL
                     AND e_tgt.id IS NULL
                   ORDER BY n.created_at ASC"""
            ).fetchall()
        except Exception:
            logger.warning("Failed to find orphaned nodes", exc_info=True)
            return []

        cols = ["id", "node_type", "title", "created_at"]
        return [dict(zip(cols, row)) for row in rows]

    def _find_stalled_goals(self, stall_days: int = 14) -> list[dict[str, Any]]:
        """Find GOAL nodes with status=active but no PROGRESS edges recently."""
        cutoff = (datetime.utcnow() - timedelta(days=stall_days)).isoformat()
        try:
            rows = self._repo._conn.execute(
                """SELECT n.id, n.title, n.properties, n.updated_at
                   FROM nodes n
                   WHERE n.deleted = FALSE
                     AND n.node_type = 'GOAL'
                     AND json_extract_string(n.properties, '$.status') = 'active'
                     AND NOT EXISTS (
                         SELECT 1 FROM edges e
                         WHERE (e.source_id = n.id OR e.target_id = n.id)
                           AND e.created_at >= ?
                     )
                   ORDER BY n.updated_at ASC""",
                [cutoff],
            ).fetchall()
        except Exception:
            logger.warning("Failed to find stalled goals", exc_info=True)
            return []

        cols = ["id", "title", "properties", "updated_at"]
        results: list[dict[str, Any]] = []
        for row in rows:
            d = dict(zip(cols, row))
            if isinstance(d["properties"], str):
                try:
                    d["properties"] = json.loads(d["properties"])
                except (json.JSONDecodeError, TypeError):
                    d["properties"] = {}
            d["stall_days"] = stall_days
            results.append(d)
        return results

    def _find_dead_end_projects(self, stall_days: int = 14) -> list[dict[str, Any]]:
        """Find PROJECT nodes with status=active but no recent edge activity."""
        cutoff = (datetime.utcnow() - timedelta(days=stall_days)).isoformat()
        try:
            rows = self._repo._conn.execute(
                """SELECT n.id, n.title, n.properties, n.updated_at
                   FROM nodes n
                   WHERE n.deleted = FALSE
                     AND n.node_type = 'PROJECT'
                     AND json_extract_string(n.properties, '$.status') = 'active'
                     AND NOT EXISTS (
                         SELECT 1 FROM edges e
                         WHERE (e.source_id = n.id OR e.target_id = n.id)
                           AND e.created_at >= ?
                     )
                   ORDER BY n.updated_at ASC""",
                [cutoff],
            ).fetchall()
        except Exception:
            logger.warning("Failed to find dead-end projects", exc_info=True)
            return []

        cols = ["id", "title", "properties", "updated_at"]
        results: list[dict[str, Any]] = []
        for row in rows:
            d = dict(zip(cols, row))
            if isinstance(d["properties"], str):
                try:
                    d["properties"] = json.loads(d["properties"])
                except (json.JSONDecodeError, TypeError):
                    d["properties"] = {}
            d["stall_days"] = stall_days
            results.append(d)
        return results

    def _find_isolated_concepts(self) -> list[dict[str, Any]]:
        """Find CONCEPT nodes not linked to any EVENT, PROJECT, or COMMITMENT."""
        try:
            rows = self._repo._conn.execute(
                """SELECT n.id, n.title, n.properties, n.created_at
                   FROM nodes n
                   WHERE n.deleted = FALSE
                     AND n.node_type = 'CONCEPT'
                     AND NOT EXISTS (
                         SELECT 1 FROM edges e
                         JOIN nodes n2 ON (
                             (e.source_id = n.id AND e.target_id = n2.id)
                             OR (e.target_id = n.id AND e.source_id = n2.id)
                         )
                         WHERE n2.node_type IN ('EVENT', 'PROJECT', 'COMMITMENT')
                     )
                   ORDER BY n.created_at ASC"""
            ).fetchall()
        except Exception:
            logger.warning("Failed to find isolated concepts", exc_info=True)
            return []

        cols = ["id", "title", "properties", "created_at"]
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

    def _find_unresolved_decisions(self) -> list[dict[str, Any]]:
        """Find DECISION nodes with no outcome recorded."""
        try:
            rows = self._repo._conn.execute(
                """SELECT id, title, properties, created_at
                   FROM nodes
                   WHERE deleted = FALSE
                     AND node_type = 'DECISION'
                     AND (
                         json_extract_string(properties, '$.outcome') IS NULL
                         OR json_extract_string(properties, '$.outcome') = ''
                     )
                   ORDER BY created_at ASC"""
            ).fetchall()
        except Exception:
            logger.warning("Failed to find unresolved decisions", exc_info=True)
            return []

        cols = ["id", "title", "properties", "created_at"]
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
