"""URL change detection and content hash tracking.

Monitors configured watch targets for content changes,
using SHA-256 content hashing to detect modifications.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class WebMonitor:
    """Tracks URL content changes via content hashing.

    Uses DuckDB watch_state table for persistence.
    """

    def __init__(self, db_conn) -> None:
        self._conn = db_conn

    def get_watch_state(self, name: str) -> dict[str, Any] | None:
        """Get the current state of a watch target."""
        try:
            row = self._conn.execute(
                "SELECT name, url, content_hash, last_check, last_change, "
                "check_count, change_count, errors FROM watch_state WHERE name = ?",
                [name],
            ).fetchone()
            if row:
                return {
                    "name": row[0],
                    "url": row[1],
                    "content_hash": row[2],
                    "last_check": row[3],
                    "last_change": row[4],
                    "check_count": row[5],
                    "change_count": row[6],
                    "errors": row[7],
                }
        except Exception:
            logger.debug("Failed to get watch state for %s", name, exc_info=True)
        return None

    def get_all_states(self) -> list[dict[str, Any]]:
        """Get all watch target states."""
        try:
            rows = self._conn.execute(
                "SELECT name, url, content_hash, last_check, last_change, "
                "check_count, change_count, errors FROM watch_state ORDER BY name"
            ).fetchall()
            return [
                {
                    "name": r[0], "url": r[1], "content_hash": r[2],
                    "last_check": r[3], "last_change": r[4],
                    "check_count": r[5], "change_count": r[6], "errors": r[7],
                }
                for r in rows
            ]
        except Exception:
            return []

    def update_check(
        self,
        name: str,
        url: str,
        content: str | None,
        error: bool = False,
    ) -> bool:
        """Update watch state after checking a URL.

        Returns True if content has changed.
        """
        now = datetime.now(timezone.utc)
        changed = False

        if content is not None:
            new_hash = hashlib.sha256(content.encode()).hexdigest()
        else:
            new_hash = None

        existing = self.get_watch_state(name)

        if existing is None:
            # First check — insert new state
            try:
                self._conn.execute(
                    """INSERT INTO watch_state
                       (name, url, content_hash, last_check, last_change,
                        check_count, change_count, errors)
                       VALUES (?, ?, ?, ?, ?, 1, 0, ?)""",
                    [name, url, new_hash, now, now, 1 if error else 0],
                )
            except Exception:
                logger.error("Failed to insert watch state for %s", name, exc_info=True)
            return False

        # Check for content change
        if new_hash and existing["content_hash"] != new_hash:
            changed = True

        try:
            if error:
                self._conn.execute(
                    """UPDATE watch_state
                       SET last_check = ?, check_count = check_count + 1,
                           errors = errors + 1
                       WHERE name = ?""",
                    [now, name],
                )
            elif changed:
                self._conn.execute(
                    """UPDATE watch_state
                       SET content_hash = ?, last_check = ?, last_change = ?,
                           check_count = check_count + 1, change_count = change_count + 1
                       WHERE name = ?""",
                    [new_hash, now, now, name],
                )
            else:
                self._conn.execute(
                    """UPDATE watch_state
                       SET last_check = ?, check_count = check_count + 1
                       WHERE name = ?""",
                    [now, name],
                )
        except Exception:
            logger.error("Failed to update watch state for %s", name, exc_info=True)

        return changed

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()
