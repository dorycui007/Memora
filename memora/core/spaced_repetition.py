"""Spaced Repetition — SM-2 algorithm for knowledge review scheduling."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from memora.graph.models import parse_properties
from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)

# SM-2 default parameters
DEFAULT_EASINESS_FACTOR = 2.5
MIN_EASINESS_FACTOR = 1.3


class SpacedRepetition:
    """SM-2 spaced repetition scheduler for knowledge-graph nodes."""

    def __init__(self, repo: GraphRepository) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize_node(self, node_id: str) -> None:
        """Set initial SM-2 parameters on a node's properties."""
        now = datetime.now(timezone.utc)
        sm2_params = {
            "easiness_factor": DEFAULT_EASINESS_FACTOR,
            "repetition_number": 0,
            "interval": 0,
            "review_date": now.isoformat(),
        }
        self._merge_properties(node_id, sm2_params)
        # Also set the top-level review_date column
        try:
            self._repo.update_node_review_date(node_id, now.isoformat())
        except Exception:
            logger.warning("Failed to set review_date column for node %s", node_id)

        logger.info("Initialized SM-2 params for node %s", node_id)

    def process_review(self, node_id: str, quality: int) -> dict[str, Any]:
        """Process a review response for *node_id*.

        Args:
            node_id: The graph node being reviewed.
            quality: Review quality score, 0 (complete blackout) to 5 (perfect).

        Returns:
            Dict of the updated SM-2 parameters.
        """
        quality = max(0, min(5, quality))
        params = self._get_sm2_params(node_id)

        ef = params.get("easiness_factor", DEFAULT_EASINESS_FACTOR)
        rep = params.get("repetition_number", 0)
        interval = params.get("interval", 0)

        if quality < 3:
            # Failed review — reset
            rep = 0
            interval = 1
        else:
            if rep == 0:
                interval = 1
            elif rep == 1:
                interval = 6
            else:
                interval = round(interval * ef)
            rep += 1

        # Update easiness factor
        ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        if ef < MIN_EASINESS_FACTOR:
            ef = MIN_EASINESS_FACTOR

        next_review = datetime.now(timezone.utc) + timedelta(days=interval)

        new_params: dict[str, Any] = {
            "easiness_factor": round(ef, 4),
            "repetition_number": rep,
            "interval": interval,
            "review_date": next_review.isoformat(),
        }

        self._merge_properties(node_id, new_params)

        # Update the top-level review_date column too
        try:
            self._repo.update_node_review_date(node_id, next_review.isoformat())
        except Exception:
            logger.warning("Failed to update review_date column for node %s", node_id)

        logger.info(
            "Processed review for node %s: quality=%d, next_interval=%d days",
            node_id, quality, interval,
        )
        return new_params

    def get_review_queue(self) -> list[dict[str, Any]]:
        """Return nodes due for review (review_date <= today).

        Ordered by most overdue first, then ascending easiness factor.
        """
        now = datetime.now(timezone.utc).isoformat()
        try:
            rows = self._repo.get_review_due_nodes(now)
        except Exception:
            logger.warning("Failed to fetch review queue", exc_info=True)
            return []

        results: list[dict[str, Any]] = []
        for d in rows:
            d["properties"] = parse_properties(d["properties"])
            results.append(d)

        # Sort by: most overdue first (descending days overdue),
        # then ascending easiness_factor (harder cards first).
        now_dt = datetime.now(timezone.utc)

        def sort_key(item: dict[str, Any]) -> tuple[float, float]:
            props = item.get("properties") or {}
            review_date_str = props.get("next_review_date")
            if review_date_str:
                try:
                    review_dt = datetime.fromisoformat(str(review_date_str))
                    if review_dt.tzinfo is None:
                        review_dt = review_dt.replace(tzinfo=timezone.utc)
                    days_overdue = (now_dt - review_dt).total_seconds() / 86400
                except (ValueError, TypeError):
                    days_overdue = 0.0
            else:
                days_overdue = 0.0
            easiness = props.get("easiness_factor", DEFAULT_EASINESS_FACTOR)
            # Negate days_overdue so most overdue sorts first (ascending sort)
            return (-days_overdue, easiness)

        results.sort(key=sort_key)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_sm2_params(self, node_id: str) -> dict[str, Any]:
        """Read the current SM-2 parameters from a node's properties."""
        try:
            raw = self._repo.get_node_properties_raw(node_id)
        except Exception:
            logger.warning("Failed to read properties for node %s", node_id)
            return {}

        if not raw:
            return {}

        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return {}
        return raw

    def _merge_properties(self, node_id: str, updates: dict[str, Any]) -> None:
        """Merge *updates* into the node's existing properties JSON."""
        current = self._get_sm2_params(node_id)
        current.update(updates)
        try:
            self._repo.update_node_properties_raw(node_id, json.dumps(current))
        except Exception:
            logger.warning(
                "Failed to merge properties for node %s", node_id, exc_info=True
            )
