"""Kinetic Actions — typed graph operations with preconditions and side effects."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from memora.graph.models import (
    ActionStatus,
    ActionType,
    CommitmentStatus,
    EdgeCategory,
    EdgeType,
    GoalStatus,
    IdeaMaturity,
    NodeType,
    ProjectStatus,
)

logger = logging.getLogger(__name__)


class ActionEngine:
    """Executes typed actions on the knowledge graph with validation and audit."""

    def __init__(
        self,
        repo,
        truth_layer=None,
        health_scoring=None,
        notification_manager=None,
    ) -> None:
        self.repo = repo
        self._truth_layer = truth_layer
        self._health_scoring = health_scoring
        self._notification_manager = notification_manager
        self._registry: dict[ActionType, dict] = {
            ActionType.COMPLETE_COMMITMENT: {
                "label": "Complete Commitment",
                "node_types": [NodeType.COMMITMENT],
                "handler": self._complete_commitment,
            },
            ActionType.PROMOTE_IDEA: {
                "label": "Promote Idea to Project",
                "node_types": [NodeType.IDEA],
                "handler": self._promote_idea,
            },
            ActionType.ARCHIVE_GOAL: {
                "label": "Archive Goal",
                "node_types": [NodeType.GOAL],
                "handler": self._archive_goal,
            },
            ActionType.ADVANCE_GOAL: {
                "label": "Advance Goal",
                "node_types": [NodeType.GOAL],
                "handler": self._advance_goal,
            },
            ActionType.RECORD_OUTCOME: {
                "label": "Record Outcome",
                "node_types": [NodeType.DECISION, NodeType.GOAL, NodeType.COMMITMENT],
                "handler": self._record_outcome,
            },
            ActionType.LINK_ENTITIES: {
                "label": "Link Entities",
                "node_types": list(NodeType),
                "handler": self._link_entities,
            },
        }

    def _get_notification_manager(self):
        """Lazily resolve notification manager (same pattern as scheduler/jobs.py)."""
        if self._notification_manager is not None:
            return self._notification_manager
        try:
            from memora.core.notifications import NotificationManager
            self._notification_manager = NotificationManager(
                self.repo.get_truth_layer_conn()
            )
            return self._notification_manager
        except Exception:
            return None

    def _get_health_scoring(self):
        """Lazily resolve health scoring engine."""
        if self._health_scoring is not None:
            return self._health_scoring
        try:
            from memora.core.health_scoring import HealthScoring
            self._health_scoring = HealthScoring(self.repo)
            return self._health_scoring
        except Exception:
            return None

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

    def get_available_actions(self, node_id: str) -> list[dict]:
        """Return valid actions for a node based on its type and state."""
        node = self.repo.get_node(UUID(node_id))
        if not node:
            return []

        available = []
        for action_type, info in self._registry.items():
            if node.node_type in info["node_types"]:
                # Check preconditions
                if self._check_precondition(action_type, node):
                    available.append({
                        "action_type": action_type.value,
                        "label": info["label"],
                    })
        return available

    def execute(self, action_type: ActionType, params: dict) -> dict:
        """Execute an action and record it in the audit trail."""
        info = self._registry.get(action_type)
        if not info:
            return {"success": False, "error": f"Unknown action type: {action_type}"}

        handler = info["handler"]
        action_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        try:
            result = handler(params)
            record = {
                "id": action_id,
                "action_type": action_type.value,
                "status": ActionStatus.COMPLETED.value,
                "source_node_id": params.get("node_id"),
                "target_node_id": result.get("target_node_id"),
                "params": params,
                "result": result,
                "executed_at": now,
            }
            self.repo.record_action(record)

            # Run side effects after successful execution
            self._run_side_effects(action_type, params, result)

            return {"success": True, "action_id": action_id, **result}

        except Exception as e:
            logger.error("Action %s failed: %s", action_type, e, exc_info=True)
            record = {
                "id": action_id,
                "action_type": action_type.value,
                "status": ActionStatus.FAILED.value,
                "source_node_id": params.get("node_id"),
                "target_node_id": None,
                "params": params,
                "result": {"error": str(e)},
                "executed_at": now,
            }
            self.repo.record_action(record)
            return {"success": False, "error": str(e)}

    def _run_side_effects(self, action_type: ActionType, params: dict, result: dict) -> None:
        """Trigger cascading side effects after a successful action."""
        node_id = params.get("node_id")
        if not node_id:
            return

        try:
            node = self.repo.get_node(UUID(node_id))
            if not node:
                return

            # Recalculate health for affected networks (all state-changing actions)
            if action_type in (
                ActionType.COMPLETE_COMMITMENT,
                ActionType.ARCHIVE_GOAL,
                ActionType.ADVANCE_GOAL,
            ):
                self._recalc_network_health(node)

            # Action-specific side effects
            if action_type == ActionType.COMPLETE_COMMITMENT:
                self._notify(
                    "COMMITMENT_COMPLETED",
                    f"Commitment completed: '{node.title}'",
                    related_node_ids=[node_id],
                    priority="low",
                )

            elif action_type == ActionType.RECORD_OUTCOME:
                # Deposit outcome as a fact to the Truth Layer
                tl = self._get_truth_layer()
                if tl:
                    rating = params.get("rating", "neutral")
                    outcome_text = params.get("outcome_text", "")
                    confidence_map = {"positive": 0.9, "neutral": 0.7, "negative": 0.5, "mixed": 0.6}
                    try:
                        from memora.core.truth_layer import FactLifecycle
                        tl.deposit_fact(
                            node_id=node_id,
                            statement=f"Outcome of '{node.title}': {outcome_text} (rated {rating})",
                            confidence=confidence_map.get(rating, 0.7),
                            lifecycle=FactLifecycle.STATIC,
                            verified_by="action_engine",
                        )
                    except Exception:
                        logger.debug("Failed to deposit outcome fact", exc_info=True)

            elif action_type == ActionType.PROMOTE_IDEA:
                # Trigger bridge discovery for the new project node
                target_id = result.get("target_node_id")
                if target_id:
                    self._notify(
                        "IDEA_PROMOTED",
                        f"Idea promoted to project: '{node.title}'",
                        related_node_ids=[node_id, target_id],
                        priority="low",
                    )

            elif action_type == ActionType.ARCHIVE_GOAL:
                self._notify(
                    "GOAL_DRIFT",
                    f"Goal archived: '{node.title}'",
                    related_node_ids=[node_id],
                    priority="medium",
                )

        except Exception:
            logger.debug("Side effects for %s failed (non-fatal)", action_type, exc_info=True)

    def _recalc_network_health(self, node) -> None:
        """Recalculate health for all networks the node belongs to."""
        hs = self._get_health_scoring()
        if not hs:
            return
        for net in (node.networks or []):
            net_val = net.value if hasattr(net, "value") else net
            try:
                hs.compute_network_health(net_val)
            except Exception:
                logger.debug("Health recalc failed for %s", net_val, exc_info=True)

    def _notify(self, type_: str, message: str, related_node_ids=None, priority="low") -> None:
        """Create a notification if notification manager is available."""
        nm = self._get_notification_manager()
        if nm:
            try:
                nm.create_notification(
                    type=type_,
                    message=message,
                    related_node_ids=related_node_ids or [],
                    priority=priority,
                    trigger_condition="action_engine",
                )
            except Exception:
                logger.debug("Notification failed", exc_info=True)

    def _check_precondition(self, action_type: ActionType, node) -> bool:
        """Check if an action's preconditions are met."""
        props = node.properties or {}

        if action_type == ActionType.COMPLETE_COMMITMENT:
            status = getattr(node, "status", None) or props.get("status", "open")
            return status == CommitmentStatus.OPEN.value or status == CommitmentStatus.OPEN

        elif action_type == ActionType.PROMOTE_IDEA:
            maturity = getattr(node, "maturity", None) or props.get("maturity", "seed")
            mat_val = maturity.value if hasattr(maturity, "value") else maturity
            return mat_val != IdeaMaturity.ARCHIVED.value

        elif action_type == ActionType.ARCHIVE_GOAL:
            status = getattr(node, "status", None) or props.get("status", "active")
            stat_val = status.value if hasattr(status, "value") else status
            return stat_val == GoalStatus.ACTIVE.value

        elif action_type == ActionType.ADVANCE_GOAL:
            status = getattr(node, "status", None) or props.get("status", "active")
            stat_val = status.value if hasattr(status, "value") else status
            return stat_val == GoalStatus.ACTIVE.value

        elif action_type == ActionType.RECORD_OUTCOME:
            return True

        elif action_type == ActionType.LINK_ENTITIES:
            return True

        return False

    def _complete_commitment(self, params: dict) -> dict:
        """Mark a commitment as completed."""
        node_id = params["node_id"]
        node = self.repo.get_node(UUID(node_id))
        if not node:
            raise ValueError(f"Node {node_id} not found")
        if node.node_type != NodeType.COMMITMENT:
            raise ValueError(f"Node {node_id} is not a COMMITMENT")

        now = datetime.now(timezone.utc).isoformat()
        props = node.properties.copy()
        props["status"] = CommitmentStatus.COMPLETED.value
        props["completed_at"] = now

        self.repo.update_node(UUID(node_id), {"properties": props})
        return {"message": f"Commitment '{node.title}' marked as completed"}

    def _promote_idea(self, params: dict) -> dict:
        """Promote an idea to a project."""
        node_id = params["node_id"]
        node = self.repo.get_node(UUID(node_id))
        if not node:
            raise ValueError(f"Node {node_id} not found")
        if node.node_type != NodeType.IDEA:
            raise ValueError(f"Node {node_id} is not an IDEA")

        from memora.graph.models import ProjectNode, Edge

        # Create a new project node
        project = ProjectNode(
            title=params.get("project_title", node.title),
            content=node.content,
            networks=node.networks,
            properties={"promoted_from_idea": node_id},
            status=ProjectStatus.ACTIVE,
        )
        project.compute_content_hash()
        project_id = self.repo.create_node(project)

        # Create EVOLVED_INTO edge
        edge = Edge(
            source_id=UUID(node_id),
            target_id=project_id,
            edge_type=EdgeType.EVOLVED_INTO,
            edge_category=EdgeCategory.TEMPORAL,
        )
        self.repo.create_edge(edge)

        # Archive the idea
        props = node.properties.copy()
        props["maturity"] = IdeaMaturity.ARCHIVED.value
        self.repo.update_node(UUID(node_id), {"properties": props})

        return {
            "message": f"Idea '{node.title}' promoted to project",
            "target_node_id": str(project_id),
        }

    def _archive_goal(self, params: dict) -> dict:
        """Archive a goal as abandoned."""
        node_id = params["node_id"]
        reason = params.get("reason", "")
        node = self.repo.get_node(UUID(node_id))
        if not node:
            raise ValueError(f"Node {node_id} not found")

        props = node.properties.copy()
        props["status"] = GoalStatus.ABANDONED.value
        props["archived_reason"] = reason
        self.repo.update_node(UUID(node_id), {"properties": props})

        # Create an insight node summarizing why
        if reason:
            from memora.graph.models import InsightNode, Edge

            insight = InsightNode(
                title=f"Goal archived: {node.title}",
                content=f"Goal '{node.title}' was archived. Reason: {reason}",
                networks=node.networks,
                derived_from=[node_id],
                actionable=True,
            )
            insight.compute_content_hash()
            insight_id = self.repo.create_node(insight)

            edge = Edge(
                source_id=UUID(node_id),
                target_id=insight_id,
                edge_type=EdgeType.DERIVED_FROM,
                edge_category=EdgeCategory.PROVENANCE,
            )
            self.repo.create_edge(edge)

        return {"message": f"Goal '{node.title}' archived"}

    def _advance_goal(self, params: dict) -> dict:
        """Update goal progress and optionally add a milestone."""
        node_id = params["node_id"]
        progress = params.get("progress")
        milestone = params.get("milestone")
        node = self.repo.get_node(UUID(node_id))
        if not node:
            raise ValueError(f"Node {node_id} not found")

        props = node.properties.copy()
        if progress is not None:
            props["progress"] = max(0.0, min(1.0, float(progress)))
        if milestone:
            milestones = props.get("milestones", [])
            milestones.append({
                "text": milestone,
                "date": datetime.now(timezone.utc).isoformat(),
            })
            props["milestones"] = milestones

        self.repo.update_node(UUID(node_id), {"properties": props})
        return {"message": f"Goal '{node.title}' advanced to {props.get('progress', 0):.0%}"}

    def _record_outcome(self, params: dict) -> dict:
        """Record an outcome for a decision/goal/commitment node."""
        node_id = params["node_id"]
        outcome_text = params.get("outcome_text", "")
        rating = params.get("rating", "neutral")

        node = self.repo.get_node(UUID(node_id))
        if not node:
            raise ValueError(f"Node {node_id} not found")

        outcome_id = str(uuid4())
        self.repo.record_outcome({
            "id": outcome_id,
            "node_id": node_id,
            "node_type": node.node_type.value,
            "outcome_text": outcome_text,
            "rating": rating,
            "evidence": params.get("evidence_ids", []),
        })

        # Also update the node's outcome property if it's a decision
        if node.node_type == NodeType.DECISION:
            props = node.properties.copy()
            props["outcome"] = outcome_text
            self.repo.update_node(UUID(node_id), {"properties": props})

        return {
            "message": f"Outcome recorded for '{node.title}'",
            "outcome_id": outcome_id,
        }

    def _link_entities(self, params: dict) -> dict:
        """Create a typed edge between two nodes."""
        source_id = params["source_id"]
        target_id = params["target_id"]
        edge_type_str = params.get("edge_type", "RELATED_TO")
        edge_category_str = params.get("edge_category", "ASSOCIATIVE")

        # Validate nodes exist
        source = self.repo.get_node(UUID(source_id))
        target = self.repo.get_node(UUID(target_id))
        if not source:
            raise ValueError(f"Source node {source_id} not found")
        if not target:
            raise ValueError(f"Target node {target_id} not found")

        from memora.graph.models import Edge

        edge = Edge(
            source_id=UUID(source_id),
            target_id=UUID(target_id),
            edge_type=EdgeType(edge_type_str),
            edge_category=EdgeCategory(edge_category_str),
        )
        edge_id = self.repo.create_edge(edge)

        return {
            "message": f"Linked '{source.title}' -> '{target.title}' via {edge_type_str}",
            "edge_id": str(edge_id),
            "target_node_id": target_id,
        }
