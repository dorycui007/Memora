"""Decay Scoring — exponential decay for node relevance over time."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from math import exp, log
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

# Node type → property field containing the meaningful date
_TEMPORAL_FIELDS: dict[str, str] = {
    "EVENT": "event_date",
    "COMMITMENT": "due_date",
    "DECISION": "decision_date",
    "GOAL": "target_date",
    "PROJECT": "target_date",
    "PERSON": "last_interaction",
}

# Node types and statuses that suppress decay (pinned at 1.0)
_ACTIVE_STATUSES: dict[str, set[str]] = {
    "COMMITMENT": {"open"},
    "GOAL": {"active"},
    "PROJECT": {"active"},
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

    # ---- Helpers ----

    @staticmethod
    def _get_temporal_reference(node_type: str, properties: dict) -> datetime | None:
        """Extract the type-specific temporal anchor from node properties."""
        field = _TEMPORAL_FIELDS.get(node_type)
        if not field:
            return None
        raw = properties.get(field)
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _is_active(node_type: str, properties: dict) -> bool:
        """Return True if the node's status means it should stay pinned at 1.0."""
        allowed = _ACTIVE_STATUSES.get(node_type)
        if not allowed:
            return False
        status = properties.get("status", "")
        return str(status).lower() in allowed

    # ---- Core decay computation ----

    def compute_decay(self, t_anchor: datetime, lambda_val: float, access_count: int = 0) -> float:
        """Return e^(-effective_lambda * delta_t) where delta_t is days since *t_anchor*.

        Higher *access_count* slows decay (logarithmic damping).
        """
        now = datetime.now(timezone.utc)
        # Handle naive datetimes from DuckDB by assuming UTC
        if t_anchor.tzinfo is None:
            t_anchor = t_anchor.replace(tzinfo=timezone.utc)
        delta_days = max(0.0, (now - t_anchor).total_seconds() / 86400.0)
        effective_lambda = lambda_val / (1 + log(1 + access_count))
        return exp(-effective_lambda * delta_days)

    # ---- Batch update ----

    def batch_update_scores(self) -> int:
        """Recompute decay_score for every non-deleted node. Return count updated."""
        try:
            rows = self._repo.get_all_nodes_for_decay()
        except Exception:
            logger.warning("Failed to fetch nodes for decay scoring", exc_info=True)
            return 0

        updated = 0
        now = datetime.now(timezone.utc)
        for row in rows:
            node_id, last_accessed, networks, node_type, props, created_at, access_count = (
                row[0], row[1], row[2], row[3], row[4], row[5], row[6],
            )

            # Parse properties JSON
            properties = json.loads(props) if isinstance(props, str) else (props or {})

            # Ensure created_at is tz-aware
            if created_at is not None and isinstance(created_at, datetime) and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            elif isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)

            # Ensure last_accessed is tz-aware
            if last_accessed is not None and isinstance(last_accessed, datetime) and last_accessed.tzinfo is None:
                last_accessed = last_accessed.replace(tzinfo=timezone.utc)
            elif isinstance(last_accessed, str):
                last_accessed = datetime.fromisoformat(last_accessed)
                if last_accessed.tzinfo is None:
                    last_accessed = last_accessed.replace(tzinfo=timezone.utc)

            # Active items don't decay
            if self._is_active(node_type or "", properties):
                new_score = 1.0
            else:
                temporal_ref = self._get_temporal_reference(node_type or "", properties)

                # Future-dated items don't decay
                if temporal_ref and temporal_ref > now:
                    new_score = 1.0
                else:
                    # Effective anchor = most recent meaningful timestamp
                    candidates = [t for t in [last_accessed, temporal_ref, created_at] if t is not None]
                    t_anchor = max(candidates)  # created_at always exists, so never empty

                    # Pick the lambda for the node's primary network
                    lambda_val = self._default_lambda
                    if networks:
                        for net in networks:
                            if net in self._network_lambdas:
                                lambda_val = self._network_lambdas[net]
                                break

                    new_score = self.compute_decay(t_anchor, lambda_val, access_count or 0)

            try:
                self._repo.update_node_decay_score(node_id, new_score)
                updated += 1
            except Exception:
                logger.warning("Failed to update decay score for node %s", node_id)

        logger.info("Batch-updated decay scores for %d nodes", updated)
        return updated

    def get_decayed_nodes(self, threshold: float = 0.3) -> list[dict[str, Any]]:
        """Return nodes whose decay_score has fallen below *threshold*.

        These are candidates for resurfacing to the user.
        """
        try:
            return self._repo.get_nodes_below_decay(threshold)
        except Exception:
            logger.warning("Failed to query decayed nodes", exc_info=True)
            return []
