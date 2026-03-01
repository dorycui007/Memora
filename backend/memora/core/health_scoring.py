"""Network Health Scoring — compute health status and momentum for each network."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)

ALL_NETWORKS = [
    "ACADEMIC",
    "PROFESSIONAL",
    "FINANCIAL",
    "HEALTH",
    "PERSONAL_GROWTH",
    "SOCIAL",
    "VENTURES",
]


class HealthScoring:
    """Compute and store health snapshots for each context network."""

    def __init__(self, repo: GraphRepository) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_network_health(self, network: str) -> dict[str, Any]:
        """Compute health metrics for a single *network*.

        Returns a dict with keys: network, status, momentum,
        commitment_completion_rate, alert_ratio, staleness_flags,
        computed_at.
        """
        completion_rate = self._commitment_completion_rate(network)
        alert_ratio = self._alert_ratio(network)
        staleness_flags = self._staleness_flags(network)

        status = self._determine_status(completion_rate, alert_ratio, staleness_flags)

        previous = self._get_previous_snapshot(network)
        momentum = self._determine_momentum(
            completion_rate, alert_ratio, previous
        )

        health: dict[str, Any] = {
            "network": network,
            "status": status,
            "momentum": momentum,
            "commitment_completion_rate": completion_rate,
            "alert_ratio": alert_ratio,
            "staleness_flags": staleness_flags,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

        self._store_snapshot(health)
        return health

    def compute_all_networks(self) -> list[dict[str, Any]]:
        """Compute health for all seven networks."""
        results: list[dict[str, Any]] = []
        for network in ALL_NETWORKS:
            try:
                results.append(self.compute_network_health(network))
            except Exception:
                logger.warning(
                    "Failed to compute health for network %s", network, exc_info=True
                )
        return results

    # ------------------------------------------------------------------
    # Status / momentum logic
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_status(
        completion_rate: float,
        alert_ratio: float,
        staleness_flags: int,
    ) -> str:
        if completion_rate < 0.4 or alert_ratio > 0.3 or staleness_flags >= 2:
            return "falling_behind"
        if (0.4 <= completion_rate < 0.7) or (0.1 <= alert_ratio <= 0.3):
            return "needs_attention"
        return "on_track"

    @staticmethod
    def _determine_momentum(
        completion_rate: float,
        alert_ratio: float,
        previous: dict[str, Any] | None,
    ) -> str:
        if previous is None:
            return "stable"
        prev_rate = previous.get("commitment_completion_rate", 0.0)
        prev_alert = previous.get("alert_ratio", 0.0)
        # Simple heuristic: compare current vs previous
        if completion_rate > prev_rate + 0.05 and alert_ratio < prev_alert:
            return "up"
        if completion_rate < prev_rate - 0.05 or alert_ratio > prev_alert + 0.05:
            return "down"
        return "stable"

    # ------------------------------------------------------------------
    # Metric helpers (DuckDB queries)
    # ------------------------------------------------------------------

    def _commitment_completion_rate(self, network: str) -> float:
        """Fraction of commitments in *network* that are completed."""
        try:
            row = self._repo._conn.execute(
                """SELECT
                       COUNT(*) FILTER (WHERE json_extract_string(properties, '$.status') = 'completed') AS done,
                       COUNT(*) AS total
                   FROM nodes
                   WHERE deleted = FALSE
                     AND node_type = 'COMMITMENT'
                     AND list_contains(networks, ?)""",
                [network],
            ).fetchone()
            total = row[1] if row else 0
            if total == 0:
                return 1.0  # No commitments counts as healthy
            return row[0] / total
        except Exception:
            logger.warning("Failed to compute completion rate for %s", network)
            return 1.0

    def _alert_ratio(self, network: str) -> float:
        """Fraction of open commitments that are overdue."""
        try:
            row = self._repo._conn.execute(
                """SELECT
                       COUNT(*) FILTER (
                           WHERE json_extract_string(properties, '$.status') = 'open'
                             AND json_extract_string(properties, '$.due_date') < ?
                       ) AS overdue,
                       COUNT(*) FILTER (
                           WHERE json_extract_string(properties, '$.status') = 'open'
                       ) AS open_total
                   FROM nodes
                   WHERE deleted = FALSE
                     AND node_type = 'COMMITMENT'
                     AND list_contains(networks, ?)""",
                [datetime.now(timezone.utc).isoformat(), network],
            ).fetchone()
            open_total = row[1] if row else 0
            if open_total == 0:
                return 0.0
            return row[0] / open_total
        except Exception:
            logger.warning("Failed to compute alert ratio for %s", network)
            return 0.0

    def _staleness_flags(self, network: str) -> int:
        """Count of nodes in *network* whose decay_score < 0.3."""
        try:
            row = self._repo._conn.execute(
                """SELECT COUNT(*)
                   FROM nodes
                   WHERE deleted = FALSE
                     AND decay_score < 0.3
                     AND list_contains(networks, ?)""",
                [network],
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            logger.warning("Failed to compute staleness flags for %s", network)
            return 0

    # ------------------------------------------------------------------
    # Snapshot persistence
    # ------------------------------------------------------------------

    def _store_snapshot(self, health: dict[str, Any]) -> None:
        """Persist a health snapshot into the network_health table."""
        try:
            self._repo._conn.execute(
                """INSERT INTO network_health
                   (id, network, status, momentum, commitment_completion_rate,
                    alert_ratio, staleness_flags, computed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    str(uuid4()),
                    health["network"],
                    health["status"],
                    health["momentum"],
                    health["commitment_completion_rate"],
                    health["alert_ratio"],
                    health["staleness_flags"],
                    health["computed_at"],
                ],
            )
        except Exception:
            logger.warning("Failed to store health snapshot", exc_info=True)

    def _get_previous_snapshot(self, network: str) -> dict[str, Any] | None:
        """Retrieve the most recent stored snapshot for *network* (for momentum)."""
        try:
            row = self._repo._conn.execute(
                """SELECT status, momentum, commitment_completion_rate,
                          alert_ratio, staleness_flags, computed_at
                   FROM network_health
                   WHERE network = ?
                   ORDER BY computed_at DESC
                   LIMIT 1""",
                [network],
            ).fetchone()
            if not row:
                return None
            cols = [
                "status", "momentum", "commitment_completion_rate",
                "alert_ratio", "staleness_flags", "computed_at",
            ]
            return dict(zip(cols, row))
        except Exception:
            logger.warning("Failed to get previous snapshot for %s", network)
            return None
