"""Timeline route — chronological view of events and deadlines."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from memora.api.deps import get_repo
from memora.graph.repository import GraphRepository

router = APIRouter()


@router.get("/timeline")
async def get_timeline(
    start: str | None = None,
    end: str | None = None,
    networks: str | None = None,
    limit: int = Query(default=100, le=500),
    repo: GraphRepository = Depends(get_repo),
):
    """Get timeline events within a date range."""
    from memora.core.timeline import TimelineEngine

    engine = TimelineEngine(repo)

    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None
    network_list = networks.split(",") if networks else None

    items = engine.get_timeline(
        start=start_dt,
        end=end_dt,
        networks=network_list,
        limit=limit,
    )
    return {"items": items, "count": len(items)}
