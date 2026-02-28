"""Notification System — store and manage user notifications."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# ── Notification type constants ──────────────────────────────────────

DEADLINE_APPROACHING = "deadline_approaching"
RELATIONSHIP_DECAY = "relationship_decay"
STALE_COMMITMENT = "stale_commitment"
HEALTH_DROP = "health_drop"
BRIDGE_DISCOVERED = "bridge_discovered"
GOAL_DRIFT = "goal_drift"
REVIEW_DUE = "review_due"

# ── Schema DDL ───────────────────────────────────────────────────────

NOTIFICATIONS_DDL = """
CREATE TABLE IF NOT EXISTS notifications (
    id                VARCHAR PRIMARY KEY,
    type              VARCHAR NOT NULL,
    trigger_condition VARCHAR DEFAULT '',
    message           TEXT NOT NULL,
    related_node_ids  JSON DEFAULT '[]',
    priority          VARCHAR DEFAULT 'medium',
    read              BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Priority ordering for queries (critical > high > medium > low).
_PRIORITY_ORDER = """
CASE priority
    WHEN 'critical' THEN 0
    WHEN 'high'     THEN 1
    WHEN 'medium'   THEN 2
    WHEN 'low'      THEN 3
    ELSE 4
END
"""

# ── Column list for SELECT statements ───────────────────────────────

_COLUMNS = (
    "id", "type", "trigger_condition", "message",
    "related_node_ids", "priority", "read", "created_at",
)

_SELECT_COLS = ", ".join(_COLUMNS)


def _row_to_dict(row: tuple) -> dict[str, Any]:
    """Convert a raw row tuple into a notification dict."""
    d = dict(zip(_COLUMNS, row))
    # Parse the JSON array stored as a string.
    if isinstance(d["related_node_ids"], str):
        try:
            d["related_node_ids"] = json.loads(d["related_node_ids"])
        except (json.JSONDecodeError, TypeError):
            d["related_node_ids"] = []
    # Ensure created_at is an ISO string for JSON-friendliness.
    if isinstance(d["created_at"], datetime):
        d["created_at"] = d["created_at"].isoformat()
    return d


class NotificationManager:
    """Create, query, and manage user notifications backed by DuckDB.

    Optionally publishes events to the SSE manager for real-time push.
    """

    def __init__(self, conn, sse_manager=None) -> None:
        self._conn = conn
        self._sse_manager = sse_manager
        self._ensure_table()

    # ── Setup ────────────────────────────────────────────────────────

    def _ensure_table(self) -> None:
        """Create the notifications table if it does not already exist."""
        try:
            self._conn.execute(NOTIFICATIONS_DDL)
        except Exception:
            logger.error("Failed to create notifications table", exc_info=True)

    # ── Write operations ─────────────────────────────────────────────

    def create_notification(
        self,
        type: str,
        message: str,
        related_node_ids: list[str] | None = None,
        priority: str = "medium",
        trigger_condition: str = "",
    ) -> str:
        """Insert a new notification and return its id."""
        nid = str(uuid4())
        node_ids_json = json.dumps(related_node_ids or [])
        try:
            self._conn.execute(
                """INSERT INTO notifications
                   (id, type, trigger_condition, message,
                    related_node_ids, priority, read, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, FALSE, ?)""",
                [
                    nid,
                    type,
                    trigger_condition,
                    message,
                    node_ids_json,
                    priority,
                    datetime.utcnow().isoformat(),
                ],
            )
            logger.debug("Created notification %s [%s]: %s", nid, type, message[:80])

            # Publish to SSE if manager is available
            if self._sse_manager:
                try:
                    import asyncio
                    event_data = {
                        "id": nid,
                        "type": type,
                        "message": message,
                        "priority": priority,
                        "related_node_ids": related_node_ids or [],
                    }
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(
                            self._sse_manager.publish(f"notification_{type}", event_data)
                        )
                    else:
                        loop.run_until_complete(
                            self._sse_manager.publish(f"notification_{type}", event_data)
                        )
                except Exception:
                    logger.debug("SSE publish failed for notification", exc_info=True)

        except Exception:
            logger.error("Failed to create notification", exc_info=True)
        return nid

    def mark_read(self, notification_id: str) -> None:
        """Mark a single notification as read."""
        try:
            self._conn.execute(
                "UPDATE notifications SET read = TRUE WHERE id = ?",
                [notification_id],
            )
        except Exception:
            logger.error(
                "Failed to mark notification %s as read",
                notification_id,
                exc_info=True,
            )

    def mark_all_read(self) -> None:
        """Mark every unread notification as read."""
        try:
            self._conn.execute("UPDATE notifications SET read = TRUE WHERE read = FALSE")
        except Exception:
            logger.error("Failed to mark all notifications as read", exc_info=True)

    # ── Read operations ──────────────────────────────────────────────

    def get_unread(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return unread notifications ordered by priority then recency."""
        try:
            rows = self._conn.execute(
                f"""SELECT {_SELECT_COLS}
                    FROM notifications
                    WHERE read = FALSE
                    ORDER BY {_PRIORITY_ORDER}, created_at DESC
                    LIMIT ?""",
                [limit],
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        except Exception:
            logger.error("Failed to fetch unread notifications", exc_info=True)
            return []

    def get_notifications(
        self,
        type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query notifications with optional type filter, paging support."""
        conditions: list[str] = []
        params: list[Any] = []

        if type is not None:
            conditions.append("type = ?")
            params.append(type)

        where = " AND ".join(conditions) if conditions else "1=1"
        params.extend([limit, offset])

        try:
            rows = self._conn.execute(
                f"""SELECT {_SELECT_COLS}
                    FROM notifications
                    WHERE {where}
                    ORDER BY {_PRIORITY_ORDER}, created_at DESC
                    LIMIT ? OFFSET ?""",
                params,
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        except Exception:
            logger.error("Failed to fetch notifications", exc_info=True)
            return []

    # ── Cleanup ──────────────────────────────────────────────────────

    def delete_old(self, days: int = 30) -> int:
        """Delete *read* notifications older than *days*. Return count deleted."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        try:
            result = self._conn.execute(
                "DELETE FROM notifications WHERE read = TRUE AND created_at < ? RETURNING id",
                [cutoff],
            ).fetchall()
            deleted = len(result)
            if deleted:
                logger.info("Deleted %d old read notifications (older than %d days)", deleted, days)
            return deleted
        except Exception:
            logger.error("Failed to delete old notifications", exc_info=True)
            return 0
