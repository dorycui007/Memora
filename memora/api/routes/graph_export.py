"""Graph export route — subgraph data for vis.js rendering."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from memora.api.deps import get_repo
from memora.graph.repository import GraphRepository

router = APIRouter()


@router.get("/graph/subgraph")
async def get_subgraph(
    center: str | None = None,
    hops: int = Query(default=2, le=5),
    limit: int = Query(default=200, le=1000),
    repo: GraphRepository = Depends(get_repo),
):
    """Get a subgraph centered on an entity for vis.js rendering.

    If no center is provided, returns the full graph (up to limit).
    """
    from memora.graph.models import NodeFilter
    from memora.graph.ontology_registry import get_ontology_registry

    registry = get_ontology_registry()

    if center:
        subgraph = repo.get_neighborhood(center, hops=hops)
        nodes_list = subgraph.nodes
        edges_list = subgraph.edges
    else:
        nodes_list = repo.query_nodes(NodeFilter(limit=limit))
        edges_list = []
        node_ids = [str(n.id) for n in nodes_list]
        if node_ids:
            edges_list = repo.get_edges_batch(node_ids)

    # Format for vis.js
    vis_nodes = []
    for n in nodes_list:
        ntype = n.node_type.value if hasattr(n.node_type, "value") else str(n.node_type)
        display = registry.get_display_config(ntype)
        vis_nodes.append({
            "id": str(n.id),
            "label": n.title,
            "node_type": ntype,
            "color": display["color"],
            "icon": display["icon"],
            "networks": [net.value if hasattr(net, "value") else str(net) for net in n.networks],
            "decay_score": n.decay_score,
            "confidence": n.confidence,
        })

    vis_edges = []
    for e in edges_list:
        vis_edges.append({
            "from": str(e.source_id),
            "to": str(e.target_id),
            "edge_type": e.edge_type.value if hasattr(e.edge_type, "value") else str(e.edge_type),
            "weight": e.weight,
            "id": str(e.id),
        })

    return {"nodes": vis_nodes, "edges": vis_edges}


@router.get("/graph/stats")
async def get_graph_stats(repo: GraphRepository = Depends(get_repo)):
    """Get graph statistics."""
    return repo.get_graph_stats()
