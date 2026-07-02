"""Watch Agent — autonomous web monitoring with content-hash change detection.

Checks configured URL targets on schedule, detects content changes,
and triggers LLM extraction for significant changes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import yaml

from memora.core.web_monitor import WebMonitor

logger = logging.getLogger(__name__)


class WatchAgent:
    """Autonomous web monitoring agent.

    Processing flow:
    1. Load watch targets from watches.yaml
    2. For each target due for checking:
       a. Fetch URL content
       b. Compute content hash
       c. Compare with stored hash
       d. If changed: extract diff, send to pipeline
    3. Publish events for changes
    """

    def __init__(
        self,
        db_conn,
        event_bus=None,
        settings=None,
    ) -> None:
        self._monitor = WebMonitor(db_conn)
        self._event_bus = event_bus
        self._settings = settings
        self._targets: list[dict[str, Any]] = []
        self._load_targets()

    def _load_targets(self) -> None:
        """Load watch targets from watches.yaml."""
        if not self._settings:
            return

        watches_path = getattr(self._settings, "watches_path", None)
        if not watches_path or not watches_path.exists():
            logger.debug("No watches.yaml found")
            return

        try:
            with open(watches_path) as f:
                data = yaml.safe_load(f) or {}
            self._targets = data.get("watches", [])
            logger.info("Loaded %d watch targets", len(self._targets))
        except Exception:
            logger.warning("Failed to load watches.yaml", exc_info=True)

    @property
    def targets(self) -> list[dict[str, Any]]:
        """Return configured watch targets."""
        return self._targets

    async def check_all(self) -> list[dict[str, Any]]:
        """Check all watch targets that are due.

        Returns a list of changes detected.
        """
        changes: list[dict[str, Any]] = []

        for target in self._targets:
            name = target.get("name", "")
            url = target.get("url", "")
            interval_hours = target.get("interval_hours", 24)

            if not name or not url:
                continue

            # Check if target is due
            state = self._monitor.get_watch_state(name)
            if state and state.get("last_check"):
                last_check = state["last_check"]
                if isinstance(last_check, datetime):
                    hours_since = (datetime.now(timezone.utc) - last_check).total_seconds() / 3600
                    if hours_since < interval_hours:
                        continue

            # Fetch and check
            try:
                content = await self._fetch_url(url)
                changed = self._monitor.update_check(name, url, content)

                if changed:
                    change = {
                        "name": name,
                        "url": url,
                        "network": target.get("network", ""),
                        "alert_on": target.get("alert_on", []),
                        "content_preview": content[:500] if content else "",
                    }
                    changes.append(change)

                    # Publish event
                    if self._event_bus:
                        await self._event_bus.publish(
                            "scraper.change",
                            {
                                "name": name,
                                "url": url,
                                "network": target.get("network", ""),
                            },
                            source="watch_agent",
                            priority=3,
                        )

                    logger.info("Watch target '%s' changed", name)

            except Exception as e:
                self._monitor.update_check(name, url, None, error=True)
                logger.warning("Watch check failed for '%s': %s", name, e)

        return changes

    async def check_single(self, name: str) -> dict[str, Any] | None:
        """Check a single watch target by name."""
        target = next((t for t in self._targets if t.get("name") == name), None)
        if not target:
            return None

        url = target.get("url", "")
        try:
            content = await self._fetch_url(url)
            changed = self._monitor.update_check(name, url, content)
            return {
                "name": name,
                "url": url,
                "changed": changed,
                "content_length": len(content) if content else 0,
            }
        except Exception as e:
            self._monitor.update_check(name, url, None, error=True)
            return {"name": name, "url": url, "error": str(e)}

    async def _fetch_url(self, url: str) -> str:
        """Fetch URL content using httpx."""
        import httpx

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={
                "User-Agent": "Memora/2.0 (Personal Intelligence Platform)",
            })
            response.raise_for_status()
            return response.text

    def get_status(self) -> list[dict[str, Any]]:
        """Get status of all watch targets."""
        states = self._monitor.get_all_states()
        state_map = {s["name"]: s for s in states}

        result = []
        for target in self._targets:
            name = target.get("name", "")
            state = state_map.get(name, {})
            result.append({
                "name": name,
                "url": target.get("url", ""),
                "network": target.get("network", ""),
                "interval_hours": target.get("interval_hours", 24),
                "last_check": state.get("last_check"),
                "last_change": state.get("last_change"),
                "check_count": state.get("check_count", 0),
                "change_count": state.get("change_count", 0),
                "errors": state.get("errors", 0),
            })

        return result
