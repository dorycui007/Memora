"""Briefing route — daily strategic intelligence briefing."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from memora.api.deps import get_repo, get_settings, get_vector_store, get_embedding_engine
from memora.graph.repository import GraphRepository

router = APIRouter()


@router.get("/briefing")
async def get_briefing(
    repo: GraphRepository = Depends(get_repo),
    settings=Depends(get_settings),
    vector_store=Depends(get_vector_store),
    embedding_engine=Depends(get_embedding_engine),
):
    """Generate a strategic daily briefing."""
    from memora.core.briefing import BriefingCollector, get_last_briefing_time

    since = get_last_briefing_time(repo)
    collector = BriefingCollector(repo)
    briefing_data = collector.collect(since=since)

    # Try strategist synthesis
    api_key = getattr(settings, "openai_api_key", "") if settings else ""
    if api_key:
        try:
            from memora.agents.strategist import StrategistAgent

            strategist = StrategistAgent(
                api_key=api_key,
                repo=repo,
                vector_store=vector_store,
                embedding_engine=embedding_engine,
            )
            briefing = await strategist.generate_briefing(briefing_data)
            return {
                "summary": briefing.summary,
                "urgent": briefing.urgent,
                "upcoming": briefing.upcoming,
                "people_followup": briefing.people_followup,
                "wins": briefing.wins,
                "stalled_attention": briefing.stalled_attention,
                "review_items": briefing.review_items,
                "positions": briefing_data.get("positions", []),
                "deadlines": briefing_data.get("deadlines", []),
            }
        except Exception:
            pass

    # Fallback: return raw briefing data
    return {"summary": "Briefing data collected.", "data": briefing_data}
