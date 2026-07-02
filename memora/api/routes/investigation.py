"""Investigation route — entity deep-dive and path-finding."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from memora.api.deps import get_repo, get_vector_store, get_embedding_engine
from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/investigate/{entity_id}")
async def investigate_entity(
    entity_id: str,
    repo: GraphRepository = Depends(get_repo),
    vector_store=Depends(get_vector_store),
    embedding_engine=Depends(get_embedding_engine),
):
    """Deep investigation of an entity: properties, connections, facts."""
    node = repo.get_node(entity_id)
    if not node:
        raise HTTPException(404, "Entity not found")

    from memora.api.routes.entities import _node_to_dict

    # Get edges and derive neighbors
    edges = repo.get_edges(entity_id)
    neighbor_ids = set()
    for e in edges:
        neighbor_ids.add(str(e.source_id))
        neighbor_ids.add(str(e.target_id))
    neighbor_ids.discard(entity_id)
    neighbors_batch = repo.get_nodes_batch(list(neighbor_ids)) if neighbor_ids else {}
    neighbors = [
        {"id": nid, "title": n.title, "node_type": n.node_type.value if hasattr(n.node_type, "value") else str(n.node_type)}
        for nid, n in neighbors_batch.items()
    ]

    # Get verified facts
    facts = []
    facts_unavailable = False
    try:
        from memora.core.truth_layer import TruthLayer
        tl = TruthLayer(repo.get_truth_layer_conn())
        facts = tl.query_facts(entity_id)
    except Exception:
        logger.warning("Truth layer query failed for entity %s", entity_id, exc_info=True)
        facts_unavailable = True

    result = {
        "entity": _node_to_dict(node),
        "neighbors": neighbors,
        "edges": [
            {
                "id": str(e.id),
                "source_id": str(e.source_id),
                "target_id": str(e.target_id),
                "edge_type": e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type),
                "weight": e.weight,
            }
            for e in edges
        ],
        "facts": facts,
    }
    if facts_unavailable:
        result["warnings"] = ["Verified facts unavailable — truth layer query failed"]
    return result


@router.get("/investigate/path")
async def find_path(
    source_id: str = Query(...),
    target_id: str = Query(...),
    max_hops: int = Query(default=5, le=10),
    repo: GraphRepository = Depends(get_repo),
):
    """Find shortest path between two entities."""
    path = repo.find_shortest_path(source_id, target_id, max_depth=max_hops)
    return {"path": path or [], "source_id": source_id, "target_id": target_id}
