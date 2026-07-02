"""In-process async event bus with priority queue and persistent log.

All subsystems communicate through events. Processing is triggered by events,
not schedules (though schedules still emit events).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass(order=True)
class Event:
    """A prioritized event in the bus."""

    priority: int
    event_type: str = field(compare=False)
    payload: dict[str, Any] = field(compare=False, default_factory=dict)
    source: str = field(compare=False, default="")
    id: str = field(compare=False, default_factory=lambda: str(uuid4()))
    created_at: datetime = field(
        compare=False, default_factory=lambda: datetime.now(timezone.utc)
    )


# Type alias for event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """In-process async event bus with wildcard subscriptions and persistent logging.

    Supports:
    - Priority-based event ordering (lower number = higher priority)
    - Wildcard pattern subscriptions (e.g., "entity.*" matches "entity.created")
    - Persistent event logging to DuckDB
    - Graceful shutdown with drain
    """

    def __init__(self, db_conn=None, max_queue_size: int = 10000) -> None:
        self._queue: asyncio.PriorityQueue[Event] = asyncio.PriorityQueue(
            maxsize=max_queue_size
        )
        self._subscribers: list[tuple[str, EventHandler]] = []
        self._running = False
        self._consumer_task: asyncio.Task | None = None
        self._db_conn = db_conn
        self._event_count = 0
        self._error_count = 0

    @property
    def event_count(self) -> int:
        """Total events processed since start."""
        return self._event_count

    @property
    def queue_size(self) -> int:
        """Current number of events in the queue."""
        return self._queue.qsize()

    # ── Pub/Sub ──────────────────────────────────────────────────

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        source: str = "",
        priority: int = 5,
    ) -> str:
        """Publish an event to the bus.

        Args:
            event_type: Dotted event name (e.g., "entity.created").
            payload: Event data dict.
            source: Identifier of the publishing subsystem.
            priority: 1 (highest) to 10 (lowest). Default 5.

        Returns:
            The event ID.
        """
        event = Event(
            priority=priority,
            event_type=event_type,
            payload=payload or {},
            source=source,
        )

        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "Event bus queue full, dropping event %s from %s",
                event_type,
                source,
            )
            return event.id

        logger.debug("Published event %s (priority=%d, source=%s)", event_type, priority, source)
        return event.id

    def subscribe(self, pattern: str, handler: EventHandler) -> None:
        """Subscribe to events matching a pattern.

        Patterns support:
        - Exact match: "entity.created"
        - Wildcard suffix: "entity.*" matches "entity.created", "entity.updated"
        - Global wildcard: "*" matches everything
        """
        self._subscribers.append((pattern, handler))
        logger.debug("Subscribed handler to pattern '%s'", pattern)

    def _matches(self, pattern: str, event_type: str) -> bool:
        """Check if an event type matches a subscription pattern."""
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event_type.startswith(prefix + ".")
        return pattern == event_type

    # ── Lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the event consumer loop."""
        if self._running:
            return
        self._running = True
        self._consumer_task = asyncio.create_task(self._consume_loop())
        logger.info("EventBus started")

    async def stop(self) -> None:
        """Stop the consumer loop and drain remaining events."""
        if not self._running:
            return
        self._running = False

        # Drain remaining events with a timeout
        try:
            await asyncio.wait_for(self._drain(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("EventBus drain timed out, %d events remaining", self._queue.qsize())

        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        logger.info(
            "EventBus stopped. Processed %d events, %d errors.",
            self._event_count,
            self._error_count,
        )

    async def _drain(self) -> None:
        """Process all remaining events in the queue."""
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                await self._dispatch(event)
            except asyncio.QueueEmpty:
                break

    # ── Consumer Loop ────────────────────────────────────────────

    async def _consume_loop(self) -> None:
        """Main consumer loop — dequeues and dispatches events."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                self._error_count += 1
                logger.error("EventBus consumer error", exc_info=True)

    async def _dispatch(self, event: Event) -> None:
        """Dispatch an event to all matching subscribers."""
        self._event_count += 1

        # Persist to event log if DB connection available (in thread to avoid blocking)
        if self._db_conn is not None:
            await asyncio.to_thread(self._log_event, event)

        handlers = [
            handler
            for pattern, handler in self._subscribers
            if self._matches(pattern, event.event_type)
        ]

        if not handlers:
            logger.debug("No handlers for event %s", event.event_type)
            return

        # Run all handlers concurrently
        results = await asyncio.gather(
            *(handler(event) for handler in handlers),
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self._error_count += 1
                logger.warning(
                    "Handler error for event %s: %s",
                    event.event_type,
                    result,
                    exc_info=result,
                )

    # ── Persistent Event Log ─────────────────────────────────────

    def _log_event(self, event: Event) -> None:
        """Persist event to DuckDB event_log table."""
        if self._db_conn is None:
            return
        try:
            import json

            self._db_conn.execute(
                """INSERT INTO event_log (id, event_type, source, payload, priority, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    event.id,
                    event.event_type,
                    event.source,
                    json.dumps(event.payload),
                    event.priority,
                    event.created_at,
                ],
            )
        except Exception:
            logger.debug("Failed to log event %s to database", event.id, exc_info=True)

    # ── Query ────────────────────────────────────────────────────

    def get_recent_events(
        self,
        event_type: str | None = None,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Query recent events from the persistent log.

        Args:
            event_type: Filter by event type pattern (supports prefix matching).
            limit: Maximum number of events to return.
            since: Only return events after this timestamp.

        Returns:
            List of event dicts, most recent first.
        """
        if self._db_conn is None:
            return []

        try:
            import json

            conditions = []
            params: list[Any] = []

            if event_type:
                if event_type.endswith(".*"):
                    conditions.append("event_type LIKE ?")
                    params.append(event_type[:-2] + ".%")
                else:
                    conditions.append("event_type = ?")
                    params.append(event_type)

            if since:
                conditions.append("created_at >= ?")
                params.append(since)

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.append(limit)

            rows = self._db_conn.execute(
                f"SELECT id, event_type, source, payload, priority, created_at "
                f"FROM event_log {where} "
                f"ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()

            return [
                {
                    "id": row[0],
                    "event_type": row[1],
                    "source": row[2],
                    "payload": json.loads(row[3]) if row[3] else {},
                    "priority": row[4],
                    "created_at": row[5],
                }
                for row in rows
            ]
        except Exception:
            logger.debug("Failed to query event log", exc_info=True)
            return []
