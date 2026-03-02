"""Outcome Tracking — feedback loop that updates confidence, deposits facts, and closes goals."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

# Confidence adjustments per rating
_CONFIDENCE_DELTA = {
    "positive": 0.1,
    "negative": -0.15,
    "mixed": 0.0,
    "neutral": 0.0,
}

_TRUTH_CONFIDENCE = {
    "positive": 0.9,
    "neutral": 0.7,
    "negative": 0.5,
    "mixed": 0.6,
}


class OutcomeTracker:
    """Track and analyze outcomes for decisions, goals, and commitments."""

    def __init__(self, repo, truth_layer=None) -> None:
        self.repo = repo
        self._truth_layer = truth_layer

    def _get_truth_layer(self):
        """Lazily resolve truth layer."""
        if self._truth_layer is not None:
            return self._truth_layer
        try:
            from memora.core.truth_layer import TruthLayer
            self._truth_layer = TruthLayer(self.repo.get_truth_layer_conn())
            return self._truth_layer
        except Exception:
            return None

    def record_outcome(
        self,
        node_id: str,
        text: str,
        rating: str,
        evidence_ids: list[str] | None = None,
    ) -> dict:
        """Record an outcome for a DECISION/GOAL/COMMITMENT node.

        Side effects:
        - Updates node confidence based on rating
        - Deposits outcome as fact to Truth Layer
        - Marks goal as achieved on positive outcome
        - Completes commitment on positive outcome
        """
        node = self.repo.get_node(UUID(node_id))
        if not node:
            raise ValueError(f"Node {node_id} not found")

        valid_types = {"DECISION", "GOAL", "COMMITMENT"}
        if node.node_type.value not in valid_types:
            raise ValueError(
                f"Cannot record outcome for {node.node_type.value} node. "
                f"Expected one of: {valid_types}"
            )

        valid_ratings = {"positive", "neutral", "negative", "mixed"}
        if rating not in valid_ratings:
            raise ValueError(f"Invalid rating '{rating}'. Expected one of: {valid_ratings}")

        outcome_id = str(uuid4())
        self.repo.record_outcome({
            "id": outcome_id,
            "node_id": node_id,
            "node_type": node.node_type.value,
            "outcome_text": text,
            "rating": rating,
            "evidence": evidence_ids or [],
        })

        # Update node's outcome property for decisions
        if node.node_type.value == "DECISION":
            props = node.properties.copy()
            props["outcome"] = text
            self.repo.update_node(UUID(node_id), {"properties": props})

        # --- Side effects: close the feedback loop ---

        # 1. Update node confidence based on rating
        self._update_confidence(node_id, node, rating)

        # 2. Deposit to Truth Layer
        self._deposit_fact(node_id, node, text, rating)

        # 3. Update goal status on positive outcome
        if node.node_type.value == "GOAL" and rating == "positive":
            self._achieve_goal(node_id, node)

        # 4. Complete commitment on positive outcome
        if node.node_type.value == "COMMITMENT" and rating == "positive":
            self._complete_commitment(node_id, node)

        return {
            "outcome_id": outcome_id,
            "node_id": node_id,
            "title": node.title,
            "rating": rating,
        }

    def _update_confidence(self, node_id: str, node, rating: str) -> None:
        """Adjust node confidence based on outcome rating."""
        delta = _CONFIDENCE_DELTA.get(rating, 0.0)
        if delta == 0.0:
            return
        try:
            new_confidence = node.confidence + delta
            new_confidence = max(0.1, min(1.0, new_confidence))
            self.repo.update_node(UUID(node_id), {"confidence": new_confidence})
        except Exception:
            logger.debug("Failed to update confidence for %s", node_id, exc_info=True)

    def _deposit_fact(self, node_id: str, node, text: str, rating: str) -> None:
        """Deposit outcome as a verified fact to the Truth Layer."""
        tl = self._get_truth_layer()
        if not tl:
            return
        try:
            from memora.core.truth_layer import FactLifecycle
            tl.deposit_fact(
                node_id=node_id,
                statement=f"Outcome of '{node.title}': {text} (rated {rating})",
                confidence=_TRUTH_CONFIDENCE.get(rating, 0.7),
                lifecycle=FactLifecycle.STATIC,
                verified_by="outcome_tracker",
            )
        except Exception:
            logger.debug("Failed to deposit outcome fact for %s", node_id, exc_info=True)

    def _achieve_goal(self, node_id: str, node) -> None:
        """Mark an active goal as achieved."""
        props = node.properties.copy()
        current_status = props.get("status", "active")
        if current_status == "active":
            props["status"] = "achieved"
            props["achieved_at"] = datetime.now(timezone.utc).isoformat()
            try:
                self.repo.update_node(UUID(node_id), {"properties": props})
            except Exception:
                logger.debug("Failed to achieve goal %s", node_id, exc_info=True)

    def _complete_commitment(self, node_id: str, node) -> None:
        """Mark an open commitment as completed."""
        props = node.properties.copy()
        current_status = props.get("status", "open")
        if current_status == "open":
            props["status"] = "completed"
            props["completed_at"] = datetime.now(timezone.utc).isoformat()
            try:
                self.repo.update_node(UUID(node_id), {"properties": props})
            except Exception:
                logger.debug("Failed to complete commitment %s", node_id, exc_info=True)

    def get_pending_outcomes(self, days_threshold: int = 14) -> list[dict]:
        """Get nodes that need outcome recording."""
        return self.repo.get_pending_outcomes(days_threshold=days_threshold)

    def get_outcome_stats(self, network: str | None = None) -> dict:
        """Get outcome statistics across the graph."""
        return self.repo.get_outcome_stats(network=network)

    def generate_outcome_prompts(self, limit: int = 5) -> list[dict]:
        """Generate natural-language prompts asking about unresolved decisions."""
        pending = self.get_pending_outcomes(days_threshold=14)

        prompts = []
        for item in pending[:limit]:
            node_type = item["node_type"]
            title = item["title"]
            created = item.get("created_at", "")

            if isinstance(created, datetime):
                age = (datetime.now(timezone.utc) - created).days
            else:
                try:
                    dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                    age = (datetime.now(timezone.utc) - dt).days
                except (ValueError, TypeError):
                    age = "?"

            if node_type == "DECISION":
                question = f"You decided '{title}' {age} days ago. How did it turn out?"
            elif node_type == "GOAL":
                question = f"Your goal '{title}' was set {age} days ago. What progress has been made?"
            elif node_type == "COMMITMENT":
                question = f"You committed to '{title}' {age} days ago. Was it fulfilled?"
            else:
                question = f"What was the outcome of '{title}'?"

            prompts.append({
                "node_id": item["id"],
                "node_type": node_type,
                "title": title,
                "age_days": age,
                "prompt": question,
            })

        return prompts
