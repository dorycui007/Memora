"""Edge routes — query graph relationships."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from memora.api.deps import get_repo
from memora.graph.repository import GraphRepository

router = APIRouter()


@router.get("/edges")
async def list_edges(
    source_id: str | None = None,
    target_id: str | None = None,
    limit: int = Query(default=100, le=1000),
    repo: GraphRepository = Depends(get_repo),
):
    """List edges with optional source/target filters."""
    results = []
    if source_id and target_id:
        results = repo.get_edges_between(source_id, target_id)
    elif source_id:
        results = repo.get_edges(source_id, "outgoing")
    elif target_id:
        results = repo.get_edges(target_id, "incoming")
    else:
        # Return recent edges
        results = repo.get_edges_batch(list(set()))  # empty
    return {
        "edges": [
            {
                "id": str(e.id),
                "source_id": str(e.source_id),
                "target_id": str(e.target_id),
                "edge_type": e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type),
                "edge_category": e.edge_category.value if hasattr(e.edge_category, "value") else str(e.edge_category),
                "confidence": e.confidence,
                "weight": e.weight,
                "bidirectional": e.bidirectional,
                "properties": e.properties,
            }
            for e in results[:limit]
        ]
    }
