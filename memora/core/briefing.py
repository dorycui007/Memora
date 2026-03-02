"""BriefingCollector — gathers data from all sources for the daily briefing."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)


def get_last_briefing_time(repo: GraphRepository) -> datetime | None:
    """Look up when the last daily briefing was generated.

    Checks the actions table for the most recent 'daily_briefing' trigger,
    falling back to notifications if needed.
    """
    try:
        actions = repo.get_actions_by_date_range(limit=200)
        for action in actions:
            params = action.get("params") or {}
            result = action.get("result") or {}
            if (
                params.get("trigger_condition") == "daily_briefing"
                or result.get("trigger_condition") == "daily_briefing"
            ):
                executed = action.get("executed_at")
                if executed:
                    if isinstance(executed, str):
                        return datetime.fromisoformat(executed.replace("Z", "+00:00"))
                    return executed
    except Exception:
        logger.debug("Could not find last briefing time from actions")

    try:
        from memora.core.notifications import NotificationManager
        conn = repo.get_truth_layer_conn()
        nm = NotificationManager(conn)
        unread = nm.get_unread(limit=200)
        for n in unread:
            if n.get("type") == "daily_briefing":
                ts = n.get("created_at")
                if ts:
                    if isinstance(ts, str):
                        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    return ts
    except Exception:
        logger.debug("Could not find last briefing time from notifications")

    return None


class BriefingCollector:
    """Collects data from all available sources for the daily briefing."""

    def __init__(
        self,
        repo: GraphRepository,
        truth_layer: Any | None = None,
    ) -> None:
        self._repo = repo
        self._truth_layer = truth_layer
        self._sources_used: list[str] = []

    def collect(self, since: datetime | None = None) -> dict[str, Any]:
        """Gather all briefing data from available sources.

        Args:
            since: Only include time-windowed data after this timestamp.
                   If None, defaults to 24 hours ago.

        Returns:
            Dict with all collected data keyed by section.
        """
        self._sources_used = []

        if since is None:
            since = datetime.now(UTC) - timedelta(hours=24)

        since_iso = since.isoformat()

        data: dict[str, Any] = {
            "date": datetime.now(UTC).date().isoformat(),
            "since": since_iso,
            "health": self._collect_health(),
            "urgent": self._collect_urgent(),
            "since_last": self._collect_since_last(since_iso),
            "upcoming": self._collect_upcoming(),
            "people": self._collect_people(),
            "patterns": self._collect_patterns(),
            "wins": self._collect_wins(since_iso),
            "stalled": self._collect_stalled(),
            "review_queue": self._collect_review_queue(),
            "truth_alerts": self._collect_truth_alerts(),
            "data_sources_used": self._sources_used,
        }

        return data

    def _collect_health(self) -> list[dict[str, Any]]:
        """Get latest health scores for all networks."""
        try:
            scores = self._repo.get_latest_health_scores()
            if scores:
                self._sources_used.append("health_scoring")
            return scores
        except Exception:
            logger.debug("Failed to collect health scores", exc_info=True)
            return []

    def _collect_urgent(self) -> dict[str, Any]:
        """Get overdue commitments, decaying close relationships, stale facts."""
        result: dict[str, Any] = {
            "overdue_commitments": [],
            "decaying_close": [],
            "stale_facts": [],
        }

        try:
            from memora.core.commitment_scan import CommitmentScanner
            scanner = CommitmentScanner(self._repo)
            scan = scanner.scan()
            result["overdue_commitments"] = scan.get("overdue", [])
            if result["overdue_commitments"]:
                self._sources_used.append("commitment_scan")
        except Exception:
            logger.debug("Failed to collect overdue commitments", exc_info=True)

        try:
            from memora.core.relationship_decay import RelationshipDecayDetector
            detector = RelationshipDecayDetector(self._repo)
            decaying = detector.scan()
            result["decaying_close"] = [
                d for d in decaying if d.get("relationship_type") == "close"
            ]
            if result["decaying_close"]:
                self._sources_used.append("relationship_decay")
        except Exception:
            logger.debug("Failed to collect decaying relationships", exc_info=True)

        if self._truth_layer:
            try:
                stale = self._truth_layer.get_stale_facts()
                result["stale_facts"] = [
                    f for f in stale if f.get("confidence", 1.0) < 0.5
                ]
                if result["stale_facts"]:
                    self._sources_used.append("truth_layer")
            except Exception:
                logger.debug("Failed to collect stale facts", exc_info=True)

        return result

    def _collect_since_last(self, since_iso: str) -> dict[str, Any]:
        """Get activity since last briefing — nodes, actions, bridges."""
        result: dict[str, Any] = {
            "new_nodes": [],
            "actions": [],
            "bridges": [],
        }

        try:
            nodes = self._repo.get_nodes_by_date_range(start=since_iso, limit=50)
            result["new_nodes"] = nodes
            if nodes:
                self._sources_used.append("timeline")
        except Exception:
            logger.debug("Failed to collect recent nodes", exc_info=True)

        try:
            actions = self._repo.get_actions_by_date_range(start=since_iso, limit=50)
            result["actions"] = actions
            if actions:
                self._sources_used.append("actions")
        except Exception:
            logger.debug("Failed to collect recent actions", exc_info=True)

        try:
            bridges = self._repo.get_recent_bridges(limit=20)
            # Filter bridges to only those discovered since last briefing
            filtered = []
            for b in bridges:
                discovered = b.get("discovered_at") or b.get("created_at", "")
                if isinstance(discovered, str) and discovered >= since_iso:
                    filtered.append(b)
            result["bridges"] = filtered if filtered else bridges[:5]
            if result["bridges"]:
                self._sources_used.append("bridges")
        except Exception:
            logger.debug("Failed to collect bridges", exc_info=True)

        return result

    def _collect_upcoming(self) -> dict[str, Any]:
        """Get approaching deadlines, pending outcomes, review queue count."""
        result: dict[str, Any] = {
            "approaching": [],
            "pending_outcomes": [],
            "review_count": 0,
        }

        try:
            from memora.core.commitment_scan import CommitmentScanner
            scanner = CommitmentScanner(self._repo)
            scan = scanner.scan()
            result["approaching"] = scan.get("approaching", [])
            if "commitment_scan" not in self._sources_used and result["approaching"]:
                self._sources_used.append("commitment_scan")
        except Exception:
            logger.debug("Failed to collect approaching commitments", exc_info=True)

        try:
            from memora.core.outcomes import OutcomeTracker
            tracker = OutcomeTracker(self._repo)
            pending = tracker.get_pending_outcomes(days_threshold=14)
            result["pending_outcomes"] = pending[:10]
            if pending:
                self._sources_used.append("outcomes")
        except Exception:
            logger.debug("Failed to collect pending outcomes", exc_info=True)

        try:
            from memora.core.spaced_repetition import SpacedRepetition
            sr = SpacedRepetition(self._repo)
            queue = sr.get_review_queue()
            result["review_count"] = len(queue) if queue else 0
            if queue:
                self._sources_used.append("spaced_repetition")
        except Exception:
            logger.debug("Failed to collect review count", exc_info=True)

        return result

    def _collect_people(self) -> dict[str, Any]:
        """Get relationship decay info and people statistics."""
        result: dict[str, Any] = {
            "decaying_all": [],
            "stats": {},
        }

        try:
            from memora.core.relationship_decay import RelationshipDecayDetector
            detector = RelationshipDecayDetector(self._repo)
            result["decaying_all"] = detector.scan()
            if "relationship_decay" not in self._sources_used and result["decaying_all"]:
                self._sources_used.append("relationship_decay")
        except Exception:
            logger.debug("Failed to collect relationship decay", exc_info=True)

        try:
            from memora.core.people_intel import PeopleIntelEngine
            engine = PeopleIntelEngine(self._repo)
            result["stats"] = engine.get_people_statistics()
            if result["stats"]:
                self._sources_used.append("people_intel")
        except Exception:
            logger.debug("Failed to collect people stats", exc_info=True)

        return result

    def _collect_patterns(self) -> list[dict[str, Any]]:
        """Get stored (previously detected) patterns."""
        try:
            patterns = self._repo.get_patterns(status="active", limit=10)
            if patterns:
                self._sources_used.append("patterns")
            return patterns
        except Exception:
            logger.debug("Failed to collect patterns", exc_info=True)
            return []

    def _collect_wins(self, since_iso: str) -> dict[str, Any]:
        """Get completed items and positive momentum since last briefing."""
        result: dict[str, Any] = {
            "completed": [],
            "momentum_up": [],
        }

        try:
            nodes = self._repo.get_nodes_by_date_range(start=since_iso, limit=100)
            result["completed"] = [
                n for n in nodes
                if (n.get("properties") or {}).get("status") in ("completed", "achieved", "done")
            ]
        except Exception:
            logger.debug("Failed to collect completed nodes", exc_info=True)

        try:
            health = self._repo.get_latest_health_scores()
            result["momentum_up"] = [
                h for h in health if h.get("momentum") == "up"
            ]
        except Exception:
            logger.debug("Failed to collect momentum data", exc_info=True)

        return result

    def _collect_stalled(self) -> dict[str, Any]:
        """Get stalled goals, dead-end projects, and other gaps."""
        try:
            from memora.core.gap_detection import GapDetector
            detector = GapDetector(self._repo)
            gaps = detector.detect_all()
            if any(v for v in gaps.values()):
                self._sources_used.append("gap_detection")
            return gaps
        except Exception:
            logger.debug("Failed to collect gap detection data", exc_info=True)
            return {}

    def _collect_review_queue(self) -> list[dict[str, Any]]:
        """Get items due for spaced repetition review."""
        try:
            from memora.core.spaced_repetition import SpacedRepetition
            sr = SpacedRepetition(self._repo)
            queue = sr.get_review_queue()
            if queue and "spaced_repetition" not in self._sources_used:
                self._sources_used.append("spaced_repetition")
            return queue or []
        except Exception:
            logger.debug("Failed to collect review queue", exc_info=True)
            return []

    def _collect_truth_alerts(self) -> list[dict[str, Any]]:
        """Get facts that need re-verification."""
        if not self._truth_layer:
            return []
        try:
            stale = self._truth_layer.get_stale_facts()
            if stale and "truth_layer" not in self._sources_used:
                self._sources_used.append("truth_layer")
            return stale
        except Exception:
            logger.debug("Failed to collect truth alerts", exc_info=True)
            return []
