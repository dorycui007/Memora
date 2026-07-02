"""Entity routes — CRUD operations for graph nodes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from memora.api.deps import get_repo
from memora.graph.models import NodeFilter
from memora.graph.repository import GraphRepository

router = APIRouter()


@router.get("/entities")
async def list_entities(
    node_type: str | None = None,
    network: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    min_confidence: float | None = None,
    min_decay_score: float | None = None,
    repo: GraphRepository = Depends(get_repo),
):
    """List entities with optional filters."""
    from memora.graph.models import NodeType, NetworkType

    filters = NodeFilter(limit=limit, offset=offset)

    if node_type:
        try:
            filters.node_types = [NodeType(node_type)]
        except ValueError:
            raise HTTPException(400, f"Invalid node type: {node_type}")

    if network:
        try:
            filters.networks = [NetworkType(network)]
        except ValueError:
            raise HTTPException(400, f"Invalid network: {network}")

    if min_confidence is not None:
        filters.min_confidence = min_confidence
    if min_decay_score is not None:
        filters.min_decay_score = min_decay_score

    nodes = repo.query_nodes(filters)
    return {"entities": [_node_to_dict(n) for n in nodes], "total": len(nodes)}


@router.get("/entities/{entity_id}")
async def get_entity(entity_id: str, repo: GraphRepository = Depends(get_repo)):
    """Get a single entity by ID."""
    node = repo.get_node(entity_id)
    if not node:
        raise HTTPException(404, "Entity not found")
    return _node_to_dict(node)


# Fields allowed in entity updates — prevents injection of arbitrary keys
_ALLOWED_UPDATE_FIELDS = frozenset({
    "title", "content", "properties", "confidence", "networks",
    "human_approved", "tags", "decay_score", "review_date",
})


class EntityUpdateRequest(BaseModel):
    updates: dict[str, Any]


@router.put("/entities/{entity_id}")
async def update_entity(
    entity_id: str,
    request: EntityUpdateRequest,
    repo: GraphRepository = Depends(get_repo),
):
    """Update an entity's properties."""
    invalid_keys = set(request.updates.keys()) - _ALLOWED_UPDATE_FIELDS
    if invalid_keys:
        raise HTTPException(400, f"Invalid update fields: {', '.join(sorted(invalid_keys))}")
    node = repo.update_node(entity_id, request.updates)
    if not node:
        raise HTTPException(404, "Entity not found")
    return _node_to_dict(node)


def _node_to_dict(node) -> dict:
    """Convert a BaseNode to a serializable dict."""
    from memora.graph.models import parse_properties

    d = {
        "id": str(node.id),
        "node_type": node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type),
        "title": node.title,
        "content": node.content,
        "properties": parse_properties(node.properties),
        "confidence": node.confidence,
        "networks": [n.value if hasattr(n, "value") else str(n) for n in node.networks],
        "decay_score": node.decay_score,
        "tags": node.tags,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
    }
    return d
