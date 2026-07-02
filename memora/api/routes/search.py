"""Search route — semantic and keyword search across the graph."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from memora.api.deps import get_repo, get_vector_store, get_embedding_engine
from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/search")
async def search_entities(
    q: str = Query(..., min_length=1, max_length=1000),
    node_type: str | None = None,
    network: str | None = None,
    limit: int = Query(default=20, le=100),
    repo: GraphRepository = Depends(get_repo),
    vector_store=Depends(get_vector_store),
    embedding_engine=Depends(get_embedding_engine),
):
    """Search entities by keyword or semantic similarity."""
    results = []
    warnings: list[str] = []

    # Try semantic search first
    if vector_store and embedding_engine:
        try:
            emb = embedding_engine.embed_text(q)
            vector_results = vector_store.dense_search(emb["dense"], top_k=limit)
            for vr in vector_results:
                r = vr.to_dict()
                node_id = r.get("node_id", "")
                ntype = r.get("node_type", "")

                if node_type and ntype != node_type:
                    continue

                node = repo.get_node(node_id)
                if node:
                    from memora.api.routes.entities import _node_to_dict
                    d = _node_to_dict(node)
                    d["score"] = r.get("score", 0.0)
                    results.append(d)
        except Exception:
            logger.warning("Semantic search failed, falling back to keyword search", exc_info=True)
            warnings.append("Semantic search unavailable, showing keyword results only")

    # Fallback to keyword search
    if not results:
        nodes = repo.search_nodes_by_content(q, limit=limit)
        for node in nodes:
            from memora.api.routes.entities import _node_to_dict
            results.append(_node_to_dict(node))

    return {"results": results, "query": q, "count": len(results), "warnings": warnings}
