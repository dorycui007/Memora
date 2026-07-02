"""Deadlines route — cross-position deadline aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from memora.api.deps import get_repo
from memora.graph.repository import GraphRepository

router = APIRouter()


@router.get("/deadlines")
async def get_deadlines(
    days: int = Query(default=30, le=365),
    repo: GraphRepository = Depends(get_repo),
):
    """Get all upcoming deadlines within N days."""
    from memora.graph.models import NodeFilter, NodeType, parse_properties

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)

    # Get commitments
    filters = NodeFilter(node_types=[NodeType.COMMITMENT], limit=500)
    commitments = repo.query_nodes(filters)

    deadlines = []
    for c in commitments:
        props = parse_properties(c.properties)
        due_str = props.get("due_date", "")
        status = props.get("status", "open")
        if not due_str or status in ("completed", "cancelled"):
            continue
        try:
            due = datetime.fromisoformat(str(due_str))
            if due <= cutoff:
                days_until = (due - now).days
                deadlines.append({
                    "id": str(c.id),
                    "title": c.title,
                    "due_date": due.isoformat(),
                    "days_until": days_until,
                    "status": status,
                    "priority": props.get("priority", "medium"),
                    "overdue": days_until < 0,
                    "networks": [n.value for n in c.networks],
                })
        except (ValueError, TypeError):
            continue

    # Sort by due date
    deadlines.sort(key=lambda d: d["due_date"])
    return {"deadlines": deadlines, "count": len(deadlines)}
