"""Graph API routes — query nodes, edges, search, stats, update, delete."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from memora.graph.models import NetworkType, NodeFilter, NodeType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


@router.get("/nodes")
async def query_nodes(
    request: Request,
    node_type: str | None = None,
    network: str | None = None,
    tag: str | None = None,
    min_confidence: float | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
):
    """Query nodes with filters."""
    repo = request.app.state.repo
    filters = NodeFilter(
        node_types=[NodeType(node_type)] if node_type else None,
        networks=[NetworkType(network)] if network else None,
        tags=[tag] if tag else None,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
    )
    nodes = repo.query_nodes(filters)
    return [n.model_dump(mode="json") for n in nodes]


@router.get("/nodes/{node_id}")
async def get_node(node_id: str, request: Request):
    """Get a single node with all properties."""
    repo = request.app.state.repo
    node = repo.get_node(UUID(node_id))
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.model_dump(mode="json")


@router.get("/nodes/{node_id}/neighborhood")
async def get_neighborhood(
    node_id: str,
    request: Request,
    hops: int = Query(default=1, ge=1, le=3),
):
    """Get 1-N hop subgraph around a node."""
    repo = request.app.state.repo
    subgraph = repo.get_neighborhood(UUID(node_id), hops=hops)
    return {
        "nodes": [n.model_dump(mode="json") for n in subgraph.nodes],
        "edges": [e.model_dump(mode="json") for e in subgraph.edges],
    }


@router.patch("/nodes/{node_id}")
async def update_node(node_id: str, request: Request, body: dict[str, Any] = {}):
    """Update node properties."""
    repo = request.app.state.repo

    # Verify node exists
    existing = repo.get_node(UUID(node_id))
    if existing is None:
        raise HTTPException(status_code=404, detail="Node not found")

    if not body:
        raise HTTPException(status_code=400, detail="No updates provided")

    node = repo.update_node(UUID(node_id), body)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.model_dump(mode="json")


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str, request: Request):
    """Soft delete a node."""
    repo = request.app.state.repo

    existing = repo.get_node(UUID(node_id))
    if existing is None:
        raise HTTPException(status_code=404, detail="Node not found")

    repo.delete_node(UUID(node_id))

    # Also remove from vector store if available
    vector_store = getattr(request.app.state, "vector_store", None)
    if vector_store:
        try:
            vector_store.delete_embedding(node_id)
        except Exception:
            pass

    return {"status": "deleted", "node_id": node_id}


@router.get("/edges")
async def get_edges(
    request: Request,
    node_id: str | None = None,
    direction: str = "both",
):
    """Query edges, optionally filtered by a node."""
    repo = request.app.state.repo
    if node_id:
        edges = repo.get_edges(UUID(node_id), direction=direction)
    else:
        edges = []
    return [e.model_dump(mode="json") for e in edges]


@router.get("/search")
async def search_graph(
    request: Request,
    q: str = Query(..., min_length=1),
    node_type: str | None = None,
    network: str | None = None,
    top_k: int = Query(default=10, le=50),
):
    """Hybrid vector + full-text search across the knowledge graph."""
    embedding_engine = _get_embedding_engine(request)
    vector_store = _get_vector_store(request)

    if not embedding_engine or not vector_store:
        raise HTTPException(
            status_code=503,
            detail="Search not available (embedding engine not initialized)",
        )

    # Generate embedding for query
    embedding = embedding_engine.embed_text(q)

    # Build filters
    filters: dict[str, Any] = {}
    if node_type:
        filters["node_type"] = node_type

    # Run hybrid search
    results = vector_store.hybrid_search(
        query_vector=embedding["dense"],
        query_text=q,
        top_k=top_k,
        filters=filters if filters else None,
    )

    # Enrich with full node data from the graph DB
    repo = request.app.state.repo
    enriched = []
    for result in results:
        node = repo.get_node(UUID(result.node_id))
        if node:
            enriched.append({
                "score": result.score,
                "node": node.model_dump(mode="json"),
            })
        else:
            enriched.append({
                "score": result.score,
                "node": result.to_dict(),
            })

    return enriched


@router.get("/stats")
async def get_stats(request: Request):
    """Node count, edge count, per-type breakdown."""
    repo = request.app.state.repo
    return repo.get_graph_stats()


@router.post("/review/{node_id}")
async def submit_review(node_id: str, request: Request, quality: int = Query(..., ge=0, le=5)):
    """Submit a spaced repetition review for a node.

    Args:
        node_id: The node UUID to review.
        quality: Review quality rating (0=blackout, 5=perfect).
    """
    from memora.core.spaced_repetition import SpacedRepetition

    repo = request.app.state.repo

    # Verify node exists
    node = repo.get_node(UUID(node_id))
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    sr = SpacedRepetition(repo)
    new_params = sr.process_review(node_id, quality)

    return {
        "node_id": node_id,
        "quality": quality,
        "updated_params": new_params,
    }


def _get_vector_store(request: Request):
    """Get or lazily initialize the vector store."""
    vector_store = getattr(request.app.state, "vector_store", None)
    if vector_store is None:
        settings = getattr(request.app.state, "settings", None)
        if settings:
            try:
                from memora.vector.store import VectorStore
                vector_store = VectorStore(db_path=settings.vector_dir)
                request.app.state.vector_store = vector_store
            except Exception:
                logger.warning("Failed to initialize vector store", exc_info=True)
    return vector_store


def _get_embedding_engine(request: Request):
    """Get or lazily initialize the embedding engine."""
    engine = getattr(request.app.state, "embedding_engine", None)
    if engine is None:
        settings = getattr(request.app.state, "settings", None)
        if settings:
            try:
                from memora.vector.embeddings import EmbeddingEngine
                engine = EmbeddingEngine(
                    model_name=settings.embedding_model,
                    cache_dir=settings.models_dir,
                )
                request.app.state.embedding_engine = engine
            except Exception:
                logger.warning("Failed to initialize embedding engine", exc_info=True)
    return engine
