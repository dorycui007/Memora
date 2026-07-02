"""Patterns route — detected behavioral patterns."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from memora.api.deps import get_repo
from memora.graph.repository import GraphRepository

router = APIRouter()


@router.get("/patterns")
async def get_patterns(
    status: str = Query(default="active"),
    limit: int = Query(default=50, le=200),
    repo: GraphRepository = Depends(get_repo),
):
    """Get detected patterns."""
    from memora.core.patterns import PatternEngine

    engine = PatternEngine(repo)
    patterns = engine.get_stored_patterns(status=status, limit=limit)
    return {"patterns": patterns, "count": len(patterns)}
