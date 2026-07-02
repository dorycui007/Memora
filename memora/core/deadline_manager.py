"""Cross-position deadline aggregation and prioritization.

Collects deadlines from commitments, goals, events, and elections
across all positions and networks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


class DeadlineManager:
    """Aggregates and prioritizes deadlines across all positions."""

    def __init__(self, repo) -> None:
        self._repo = repo

    def get_upcoming(self, days: int = 30) -> list[dict[str, Any]]:
        """Get all upcoming deadlines within N days, sorted by urgency."""
        from memora.graph.models import NodeFilter, NodeType, parse_properties

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days)
        deadlines: list[dict[str, Any]] = []

        # Commitments
        for ntype, date_field in [
            (NodeType.COMMITMENT, "due_date"),
            (NodeType.EVENT, "event_date"),
            (NodeType.GOAL, "target_date"),
        ]:
            filters = NodeFilter(node_types=[ntype], limit=500)
            nodes = self._repo.query_nodes(filters)

            for node in nodes:
                props = parse_properties(node.properties)
                date_str = props.get(date_field, "")
                if not date_str:
                    continue

                # Skip completed/cancelled
                status = props.get("status", "")
                if status in ("completed", "cancelled", "achieved", "abandoned"):
                    continue

                try:
                    due = datetime.fromisoformat(str(date_str))
                    if due > cutoff:
                        continue
                    days_until = (due - now).days

                    deadlines.append({
                        "id": str(node.id),
                        "title": node.title,
                        "node_type": ntype.value,
                        "date": due.isoformat(),
                        "days_until": days_until,
                        "overdue": days_until < 0,
                        "priority": props.get("priority", "medium"),
                        "status": status,
                        "networks": [n.value for n in node.networks],
                    })
                except (ValueError, TypeError):
                    continue

        # Elections
        filters = NodeFilter(node_types=[NodeType.ELECTION], limit=100)
        elections = self._repo.query_nodes(filters)
        for node in elections:
            props = parse_properties(node.properties)
            date_str = props.get("date", "")
            if not date_str:
                continue
            result = props.get("result", "pending")
            if result != "pending":
                continue
            try:
                due = datetime.fromisoformat(str(date_str))
                if due > cutoff:
                    continue
                days_until = (due - now).days
                deadlines.append({
                    "id": str(node.id),
                    "title": node.title,
                    "node_type": "ELECTION",
                    "date": due.isoformat(),
                    "days_until": days_until,
                    "overdue": days_until < 0,
                    "priority": "high",
                    "status": "pending",
                    "networks": [n.value for n in node.networks],
                })
            except (ValueError, TypeError):
                continue

        # Sort by date
        deadlines.sort(key=lambda d: d["date"])
        return deadlines

    def get_critical(self) -> list[dict[str, Any]]:
        """Get deadlines that are overdue or due within 3 days."""
        all_deadlines = self.get_upcoming(days=3)
        return [d for d in all_deadlines if d["overdue"] or d["days_until"] <= 3]
