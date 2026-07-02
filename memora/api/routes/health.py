"""Health route — network health dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from memora.api.deps import get_repo
from memora.graph.repository import GraphRepository

router = APIRouter()


@router.get("/health")
async def get_health(repo: GraphRepository = Depends(get_repo)):
    """Get health status for all networks."""
    from memora.core.health_scoring import HealthScoring

    scorer = HealthScoring(repo)
    results = scorer.compute_all_networks()
    return {"networks": results}
