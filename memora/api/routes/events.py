"""Events route — SSE stream for real-time dashboard updates."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from memora.api.deps import get_event_bus
from memora.core.event_bus import Event, EventBus

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/events")
async def event_stream(event_bus: EventBus = Depends(get_event_bus)):
    """SSE endpoint — streams all events to connected browsers."""
    async def generate():
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)

        async def forward_event(event: Event) -> None:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Drop events if client is too slow

        event_bus.subscribe("*", forward_event)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    data = json.dumps({
                        "id": event.id,
                        "type": event.event_type,
                        "payload": event.payload,
                        "source": event.source,
                        "created_at": event.created_at.isoformat(),
                    })
                    yield f"event: {event.event_type}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/events/history")
async def get_event_history(
    event_type: str | None = None,
    limit: int = Query(default=50, le=500),
    event_bus: EventBus = Depends(get_event_bus),
):
    """Query recent events from the persistent log."""
    events = event_bus.get_recent_events(event_type=event_type, limit=limit)
    return {"events": events, "count": len(events)}
