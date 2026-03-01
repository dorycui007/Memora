"""Decay Scoring — exponential decay for node relevance over time."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from math import exp
from typing import Any

from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)

# Default decay lambdas per network (higher = faster decay)
DEFAULT_NETWORK_LAMBDAS: dict[str, float] = {
    "ACADEMIC": 0.05,
    "PROFESSIONAL": 0.03,
    "FINANCIAL": 0.02,
    "HEALTH": 0.05,
    "PERSONAL_GROWTH": 0.04,
    "SOCIAL": 0.07,
    "VENTURES": 0.03,
}


class DecayScoring:
    """Compute and update exponential decay scores for graph nodes."""

    def __init__(
        self,
        repo: GraphRepository,
        default_lambda: float = 0.01,
        network_lambdas: dict[str, float] | None = None,
    ) -> None:
        self._repo = repo
        self._default_lambda = default_lambda
        self._network_lambdas = network_lambdas or DEFAULT_NETWORK_LAMBDAS

    def compute_decay(self, t_last_access: datetime, lambda_val: float) -> float:
        """Return e^(-lambda * delta_t) where delta_t is days since *t_last_access*."""
        now = datetime.now(timezone.utc)
        # Handle naive datetimes from DuckDB by assuming UTC
        if t_last_access.tzinfo is None:
            t_last_access = t_last_access.replace(tzinfo=timezone.utc)
        delta_days = (now - t_last_access).total_seconds() / 86400.0
        if delta_days < 0:
            delta_days = 0.0
        return exp(-lambda_val * delta_days)

    def batch_update_scores(self) -> int:
        """Recompute decay_score for every non-deleted node. Return count updated."""
        from memora.graph.repository import YOU_NODE_ID

        try:
            rows = self._repo._conn.execute(
                """SELECT id, last_accessed, networks
                   FROM nodes
                   WHERE deleted = FALSE AND id != ?""",
                [YOU_NODE_ID],
            ).fetchall()
        except Exception:
            logger.warning("Failed to fetch nodes for decay scoring", exc_info=True)
            return 0

        updated = 0
        now = datetime.now(timezone.utc)
        for row in rows:
            node_id, last_accessed, networks = row[0], row[1], row[2]

            # Determine effective last-access time
            if last_accessed is None:
                # Never accessed — treat as current (score = 1.0)
                t_last = now
            else:
                t_last = last_accessed

            # Pick the lambda for the node's primary network
            lambda_val = self._default_lambda
            if networks:
                for net in networks:
                    if net in self._network_lambdas:
                        lambda_val = self._network_lambdas[net]
                        break

            new_score = self.compute_decay(t_last, lambda_val)

            try:
                self._repo._conn.execute(
                    "UPDATE nodes SET decay_score = ?, updated_at = ? WHERE id = ?",
                    [new_score, now.isoformat(), node_id],
                )
                updated += 1
            except Exception:
                logger.warning("Failed to update decay score for node %s", node_id)

        logger.info("Batch-updated decay scores for %d nodes", updated)
        return updated

    def get_decayed_nodes(self, threshold: float = 0.3) -> list[dict[str, Any]]:
        """Return nodes whose decay_score has fallen below *threshold*.

        These are candidates for resurfacing to the user.
        """
        from memora.graph.repository import YOU_NODE_ID

        try:
            rows = self._repo._conn.execute(
                """SELECT id, node_type, title, decay_score, last_accessed, networks
                   FROM nodes
                   WHERE deleted = FALSE AND decay_score < ? AND id != ?
                   ORDER BY decay_score ASC""",
                [threshold, YOU_NODE_ID],
            ).fetchall()
        except Exception:
            logger.warning("Failed to query decayed nodes", exc_info=True)
            return []

        cols = ["id", "node_type", "title", "decay_score", "last_accessed", "networks"]
        return [dict(zip(cols, row)) for row in rows]
