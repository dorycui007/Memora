"""People route — relationship directory and CRM."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from memora.api.deps import get_repo, get_vector_store, get_embedding_engine
from memora.graph.repository import GraphRepository

router = APIRouter()


@router.get("/people")
async def list_people(
    sort_by: str = Query(default="strength", enum=["strength", "name", "recency"]),
    limit: int = Query(default=50, le=200),
    repo: GraphRepository = Depends(get_repo),
    vector_store=Depends(get_vector_store),
    embedding_engine=Depends(get_embedding_engine),
):
    """List people ranked by relationship strength."""
    from memora.core.people_intel import PeopleIntelEngine

    engine = PeopleIntelEngine(
        repo=repo,
        vector_store=vector_store,
        embedding_engine=embedding_engine,
    )
    people = engine.get_ranked_people(limit=limit)
    return {"people": people, "count": len(people)}
