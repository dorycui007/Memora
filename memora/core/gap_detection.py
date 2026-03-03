"""Gap Detection — identify orphans, stalled goals, dead-end projects, and knowledge gaps."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from memora.graph.models import parse_properties
from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)


DEFAULT_STALL_DAYS = 14


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
            return self._repo.find_orphaned_nodes()
        except Exception:
            logger.warning("Failed to find orphaned nodes", exc_info=True)
            return []

    def _find_stalled_goals(self, stall_days: int = DEFAULT_STALL_DAYS) -> list[dict[str, Any]]:
        """Find GOAL nodes with status=active but no PROGRESS edges recently."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=stall_days)).isoformat()
        try:
            rows = self._repo.find_stalled_active_nodes("GOAL", cutoff)
        except Exception:
            logger.warning("Failed to find stalled goals", exc_info=True)
            return []

        results: list[dict[str, Any]] = []
        for d in rows:
            d["properties"] = parse_properties(d["properties"])
            d["stall_days"] = stall_days
            results.append(d)
        return results

    def _find_dead_end_projects(self, stall_days: int = DEFAULT_STALL_DAYS) -> list[dict[str, Any]]:
        """Find PROJECT nodes with status=active but no recent edge activity."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=stall_days)).isoformat()
        try:
            rows = self._repo.find_stalled_active_nodes("PROJECT", cutoff)
        except Exception:
            logger.warning("Failed to find dead-end projects", exc_info=True)
            return []

        results: list[dict[str, Any]] = []
        for d in rows:
            d["properties"] = parse_properties(d["properties"])
            d["stall_days"] = stall_days
            results.append(d)
        return results

    def _find_isolated_concepts(self) -> list[dict[str, Any]]:
        """Find CONCEPT nodes not linked to any EVENT, PROJECT, or COMMITMENT."""
        try:
            rows = self._repo.find_isolated_concepts()
        except Exception:
            logger.warning("Failed to find isolated concepts", exc_info=True)
            return []

        results: list[dict[str, Any]] = []
        for d in rows:
            d["properties"] = parse_properties(d["properties"])
            results.append(d)
        return results

    def _find_unresolved_decisions(self) -> list[dict[str, Any]]:
        """Find DECISION nodes with no outcome recorded."""
        try:
            rows = self._repo.find_unresolved_decisions()
        except Exception:
            logger.warning("Failed to find unresolved decisions", exc_info=True)
            return []

        results: list[dict[str, Any]] = []
        for d in rows:
            d["properties"] = parse_properties(d["properties"])
            results.append(d)
        return results
