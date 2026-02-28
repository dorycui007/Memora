"""Council API routes — multi-agent query, briefing, and critique endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from memora.api.schemas.council_schemas import (
    AgentOutput,
    AgentRole,
    BriefingSectionResponse,
    CouncilQueryRequest,
    CouncilQueryResponse,
    CritiqueRequest,
    CritiqueResponse,
    DailyBriefingResponse,
    QueryType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/council", tags=["council"])

# Cache for daily briefing
_briefing_cache: dict[str, Any] = {"date": None, "briefing": None}
_briefing_lock = asyncio.Lock()


def _get_orchestrator(request: Request):
    """Lazy-initialize and return the orchestrator."""
    if not hasattr(request.app.state, "orchestrator") or request.app.state.orchestrator is None:
        from memora.agents.orchestrator import Orchestrator

        settings = request.app.state.settings
        if not settings.openai_api_key:
            raise HTTPException(status_code=503, detail="OpenAI API key not configured")

        request.app.state.orchestrator = Orchestrator(
            api_key=settings.openai_api_key,
            repo=request.app.state.repo,
            vector_store=getattr(request.app.state, "vector_store", None),
            embedding_engine=getattr(request.app.state, "embedding_engine", None),
            truth_layer=getattr(request.app.state, "truth_layer", None),
        )
    return request.app.state.orchestrator


def _get_strategist(request: Request):
    """Lazy-initialize and return the strategist agent."""
    if not hasattr(request.app.state, "strategist") or request.app.state.strategist is None:
        from memora.agents.strategist import StrategistAgent

        settings = request.app.state.settings
        if not settings.openai_api_key:
            raise HTTPException(status_code=503, detail="OpenAI API key not configured")

        request.app.state.strategist = StrategistAgent(
            api_key=settings.openai_api_key,
            repo=request.app.state.repo,
            vector_store=getattr(request.app.state, "vector_store", None),
            embedding_engine=getattr(request.app.state, "embedding_engine", None),
            truth_layer=getattr(request.app.state, "truth_layer", None),
        )
    return request.app.state.strategist


@router.post("/query", response_model=CouncilQueryResponse)
async def council_query(body: CouncilQueryRequest, request: Request):
    """Submit a query to the AI Council.

    Routes the query to the appropriate agent(s) based on classification
    and returns a synthesized response.
    """
    orchestrator = _get_orchestrator(request)

    result = await asyncio.to_thread(
        orchestrator.run,
        body.query,
        query_type=body.query_type.value if body.query_type else None,
        context=body.context,
        max_deliberation_rounds=body.max_deliberation_rounds,
    )

    agent_outputs = []
    for output in result.agent_outputs:
        agent_name = output.get("agent", "unknown")
        try:
            agent_role = AgentRole(agent_name)
        except ValueError:
            agent_role = AgentRole.ORCHESTRATOR

        agent_outputs.append(AgentOutput(
            agent=agent_role,
            content=output.get("content", ""),
            confidence=output.get("confidence", 0.5),
            citations=output.get("citations", []),
            sources=output.get("sources", []),
        ))

    return CouncilQueryResponse(
        query_id=result.query_id,
        query_type=QueryType(result.query_type.value),
        synthesis=result.synthesis,
        agent_outputs=agent_outputs,
        confidence=result.confidence,
        citations=result.citations,
        deliberation_rounds=result.deliberation_rounds,
        high_disagreement=result.high_disagreement,
    )


@router.get("/briefing", response_model=DailyBriefingResponse)
async def get_daily_briefing(request: Request):
    """Get today's daily briefing.

    Cached per day — regenerated once daily or on first request.
    """
    global _briefing_cache
    today = datetime.now(timezone.utc).date().isoformat()

    # Return cached if available for today
    if _briefing_cache["date"] == today and _briefing_cache["briefing"]:
        cached = _briefing_cache["briefing"]
        return DailyBriefingResponse(
            sections=cached.get("sections", []),
            summary=cached.get("summary", ""),
            generated_at=cached.get("generated_at", datetime.now(timezone.utc)),
            cached=True,
        )

    async with _briefing_lock:
        # Double-check after acquiring lock (another request may have populated cache)
        if _briefing_cache["date"] == today and _briefing_cache["briefing"]:
            cached = _briefing_cache["briefing"]
            return DailyBriefingResponse(
                sections=cached.get("sections", []),
                summary=cached.get("summary", ""),
                generated_at=cached.get("generated_at", datetime.now(timezone.utc)),
                cached=True,
            )

        strategist = _get_strategist(request)
        repo = request.app.state.repo

        # Gather data from background jobs
        health_scores = _get_health_scores(repo)
        alerts = _get_alerts(repo)
        bridges = _get_recent_bridges(repo)
        commitments = _get_commitment_data(repo)
        review_items = _get_review_items(repo)

        briefing = await strategist.generate_briefing(
            health_scores=health_scores,
            alerts=alerts,
            bridges=bridges,
            commitments=commitments,
            review_items=review_items,
        )

        sections = [
            BriefingSectionResponse(
                title=s.title,
                items=s.items,
                priority=s.priority,
            )
            for s in briefing.sections
        ]

        # Cache the result
        _briefing_cache = {
            "date": today,
            "briefing": {
                "sections": [s.model_dump() for s in sections],
                "summary": briefing.summary,
                "generated_at": briefing.generated_at,
            },
        }

        return DailyBriefingResponse(
            sections=sections,
            summary=briefing.summary,
            generated_at=briefing.generated_at,
            cached=False,
        )


@router.post("/critique", response_model=CritiqueResponse)
async def critique(body: CritiqueRequest, request: Request):
    """Invoke critic mode on a statement or decision.

    Challenges assumptions using graph evidence.
    """
    strategist = _get_strategist(request)

    result = await asyncio.to_thread(
        strategist.critique,
        body.statement,
        graph_context=body.context or None,
    )

    return CritiqueResponse(
        original_statement=body.statement,
        critique=result.analysis,
        counter_evidence=[
            r.get("action", "") for r in result.recommendations
        ] if result.recommendations else [],
        confidence=result.confidence,
        citations=result.citations,
    )


# ---- WebSocket endpoint ----


@router.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket, request: Request):
    """WebSocket endpoint for streaming council query responses."""
    from memora.api.websocket import manager, stream_council_query

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            query = data.get("query", "")
            query_type = data.get("query_type")
            context = data.get("context")

            if not query:
                await manager.send_json(websocket, {
                    "type": "error",
                    "message": "Query is required",
                })
                continue

            orchestrator = _get_orchestrator(request)
            await stream_council_query(
                websocket, orchestrator, query,
                query_type=query_type, context=context,
            )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.error("WebSocket error", exc_info=True)
        manager.disconnect(websocket)


# ---- SSE endpoint ----


@router.get("/events")
async def sse_events(request: Request):
    """Server-Sent Events endpoint for background event delivery."""
    from memora.api.websocket import sse_manager

    queue = sse_manager.subscribe()

    async def event_generator():
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"event: {event['event_type']}\ndata: {json.dumps(event['data'], default=str)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f": keepalive\n\n"
        finally:
            sse_manager.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---- Helper functions for gathering briefing data ----


def _get_health_scores(repo) -> list[dict[str, Any]]:
    """Get latest health scores for all networks."""
    return repo.get_latest_health_scores()


def _get_alerts(repo) -> list[dict[str, Any]]:
    """Get active alerts (overdue commitments, stale items)."""
    return repo.get_open_commitments_raw(limit=20)


def _get_recent_bridges(repo) -> list[dict[str, Any]]:
    """Get recently discovered bridges."""
    return repo.get_recent_bridges(limit=10)


def _get_commitment_data(repo) -> dict[str, Any]:
    """Get commitment statistics."""
    try:
        from memora.core.commitment_scan import CommitmentScanner
        scanner = CommitmentScanner(repo)
        return scanner.scan()
    except Exception:
        return {}


def _get_review_items(repo) -> list[dict[str, Any]]:
    """Get items due for spaced repetition review."""
    try:
        from memora.core.spaced_repetition import SpacedRepetition
        sr = SpacedRepetition(repo)
        return sr.get_review_queue()
    except Exception:
        return []
