"""Commitment Scan — detect overdue and approaching commitments."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)


class CommitmentScanner:
    """Scan the graph for overdue and approaching commitments."""

    def __init__(self, repo: GraphRepository) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> dict[str, Any]:
        """Run a full commitment scan.

        Returns a dict with keys:
            overdue     — list of overdue commitment dicts
            approaching — list of approaching commitment dicts (each carries window_days)
            stats       — summary counts
        """
        commitments = self._get_open_commitments()

        overdue = self._check_overdue(commitments)
        approaching = self._check_approaching(commitments)

        stats = {
            "total_open": len(commitments),
            "overdue_count": len(overdue),
            "approaching_count": len(approaching),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Commitment scan complete: %d open, %d overdue, %d approaching",
            stats["total_open"],
            stats["overdue_count"],
            stats["approaching_count"],
        )

        return {
            "overdue": overdue,
            "approaching": approaching,
            "stats": stats,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_open_commitments(self) -> list[dict[str, Any]]:
        """Query all COMMITMENT nodes with status=open."""
        try:
            rows = self._repo.get_open_commitments_detailed()
        except Exception:
            logger.warning("Failed to fetch open commitments", exc_info=True)
            return []

        results: list[dict[str, Any]] = []
        for d in rows:
            # Parse properties JSON if it's a string
            if isinstance(d["properties"], str):
                try:
                    d["properties"] = json.loads(d["properties"])
                except (json.JSONDecodeError, TypeError):
                    d["properties"] = {}
            results.append(d)
        return results

    def _check_overdue(self, commitments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter commitments whose due_date is in the past."""
        now = datetime.now(timezone.utc)
        overdue: list[dict[str, Any]] = []

        for c in commitments:
            due_date = self._parse_due_date(c)
            if due_date is None:
                continue
            if due_date < now:
                overdue.append({
                    "node_id": c["id"],
                    "title": c["title"],
                    "due_date": due_date.isoformat(),
                    "days_overdue": (now - due_date).days,
                    "networks": c.get("networks"),
                })

        return overdue

    def _check_approaching(
        self,
        commitments: list[dict[str, Any]],
        windows: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Filter commitments due within the specified *windows* (days)."""
        if windows is None:
            windows = [1, 3, 7]

        now = datetime.now(timezone.utc)
        approaching: list[dict[str, Any]] = []

        for c in commitments:
            due_date = self._parse_due_date(c)
            if due_date is None:
                continue
            # Only future / today
            if due_date < now:
                continue
            days_until = (due_date - now).days
            for w in sorted(windows):
                if days_until <= w:
                    approaching.append({
                        "node_id": c["id"],
                        "title": c["title"],
                        "due_date": due_date.isoformat(),
                        "days_until_due": days_until,
                        "window_days": w,
                        "networks": c.get("networks"),
                    })
                    break  # Only match the tightest window

        return approaching

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_due_date(commitment: dict[str, Any]) -> datetime | None:
        """Extract and parse the due_date from a commitment's properties."""
        props = commitment.get("properties") or {}
        raw = props.get("due_date")
        if not raw:
            return None
        if isinstance(raw, datetime):
            return raw
        try:
            return datetime.fromisoformat(str(raw))
        except (ValueError, TypeError):
            return None
