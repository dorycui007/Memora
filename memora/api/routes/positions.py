"""Positions route — strategic position tracking."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from memora.api.deps import get_repo
from memora.graph.repository import GraphRepository

router = APIRouter()


@router.get("/positions")
async def list_positions(repo: GraphRepository = Depends(get_repo)):
    """List all tracked strategic positions with health metrics."""
    from memora.graph.models import NodeFilter, NodeType

    filters = NodeFilter(node_types=[NodeType.POSITION], limit=50)
    positions = repo.query_nodes(filters)

    results = []
    for pos in positions:
        from memora.graph.models import parse_properties

        props = parse_properties(pos.properties)
        edges = repo.get_edges(str(pos.id), "incoming")

        # Count related commitments and blockers
        commitment_count = 0
        for e in edges:
            source = repo.get_node(str(e.source_id))
            if source and source.node_type.value == "COMMITMENT":
                commitment_count += 1

        results.append({
            "id": str(pos.id),
            "title": pos.title,
            "organization": props.get("organization", ""),
            "status": props.get("status", ""),
            "holder": props.get("holder", ""),
            "blockers": props.get("blockers", []),
            "commitment_count": commitment_count,
            "decay_score": pos.decay_score,
            "networks": [n.value for n in pos.networks],
        })

    return {"positions": results, "count": len(results)}
