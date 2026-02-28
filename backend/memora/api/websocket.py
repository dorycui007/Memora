"""WebSocket handler for streaming agent responses.

Provides token-by-token streaming of council query responses with
agent state updates and metadata.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track a new WebSocket connection."""
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("WebSocket connected (%d active)", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.info("WebSocket disconnected (%d active)", len(self._connections))

    async def send_json(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        """Send JSON data to a specific connection."""
        try:
            await websocket.send_json(data)
        except Exception:
            logger.warning("Failed to send WebSocket message", exc_info=True)
            self.disconnect(websocket)

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Broadcast JSON data to all connected clients."""
        disconnected = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    @property
    def active_count(self) -> int:
        return len(self._connections)


# Global connection manager
manager = ConnectionManager()


async def stream_council_query(
    websocket: WebSocket,
    orchestrator: Any,
    query: str,
    query_type: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Stream a council query response via WebSocket.

    Sends agent state updates, token-by-token streaming for synthesis,
    and the final synthesized response.
    """
    query_id = ""

    try:
        # Notify: query received
        await manager.send_json(websocket, {
            "type": "query_received",
            "query": query,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Notify: classification starting
        await manager.send_json(websocket, {
            "type": "agent_state",
            "agent": "orchestrator",
            "state": "thinking",
            "message": "Classifying query...",
        })

        # Run the orchestrator (synchronous, but wrapped for async)
        result = await asyncio.to_thread(
            orchestrator.run,
            query,
            query_type=query_type,
            context=context,
        )
        query_id = result.query_id

        # Send agent outputs as they're available
        for output in result.agent_outputs:
            agent = output.get("agent", "unknown")

            await manager.send_json(websocket, {
                "type": "agent_state",
                "agent": agent,
                "state": "done",
                "message": f"{agent} analysis complete",
            })

            await manager.send_json(websocket, {
                "type": "agent_output",
                "agent": agent,
                "content": output.get("content", ""),
                "confidence": output.get("confidence", 0.0),
                "citations": output.get("citations", []),
            })

        # Stream synthesis token by token
        await _stream_synthesis_tokens(
            websocket, result.synthesis, query_id
        )

        # Send final synthesis metadata
        await manager.send_json(websocket, {
            "type": "synthesis",
            "query_id": query_id,
            "content": result.synthesis,
            "confidence": result.confidence,
            "citations": result.citations,
            "deliberation_rounds": result.deliberation_rounds,
            "high_disagreement": result.high_disagreement,
        })

        # Notify: complete
        await manager.send_json(websocket, {
            "type": "complete",
            "query_id": query_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

    except Exception as e:
        logger.error("WebSocket stream error: %s", e, exc_info=True)
        await manager.send_json(websocket, {
            "type": "error",
            "query_id": query_id,
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        })


async def _stream_synthesis_tokens(
    websocket: WebSocket, synthesis: str, query_id: str
) -> None:
    """Stream synthesis text token-by-token to the WebSocket client.

    Splits the synthesis into word-level tokens and sends them with small
    delays for a typewriter effect. This provides progressive rendering
    on the frontend while the full result is available.
    """
    if not synthesis:
        return

    await manager.send_json(websocket, {
        "type": "stream_start",
        "query_id": query_id,
    })

    # Split into tokens (words + punctuation groups)
    tokens = synthesis.split(" ")
    buffer = ""
    for i, token in enumerate(tokens):
        buffer += (" " if buffer else "") + token
        # Send in small chunks (every 3-5 tokens) for efficiency
        if len(buffer) >= 30 or i == len(tokens) - 1:
            await manager.send_json(websocket, {
                "type": "stream_token",
                "query_id": query_id,
                "token": buffer,
                "index": i,
                "total": len(tokens),
            })
            buffer = ""
            # Small yield to avoid flooding
            await asyncio.sleep(0.01)

    await manager.send_json(websocket, {
        "type": "stream_end",
        "query_id": query_id,
    })


class SSEManager:
    """Server-Sent Events manager for background event delivery."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        """Create a new SSE subscription queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        logger.info("SSE subscriber added (%d active)", len(self._subscribers))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove an SSE subscription."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)
        logger.info("SSE subscriber removed (%d active)", len(self._subscribers))

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to all SSE subscribers."""
        event = {
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        dead_queues = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug("SSE queue full, removing subscriber")
                dead_queues.append(queue)
        for q in dead_queues:
            self.unsubscribe(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Global SSE manager
sse_manager = SSEManager()
