"""API schemas for proposal endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProposalAction(BaseModel):
    """Single action within a proposal for human-readable display."""

    action: Literal["create_node", "update_node", "create_edge", "update_edge"]
    summary: str
    node_type: str | None = None
    edge_type: str | None = None
    confidence: float = 0.8
    impact: Literal["low", "medium", "high"] = "low"


class ProposalResponse(BaseModel):
    """List-view response for GET /proposals."""

    id: str
    capture_id: str | None = None
    status: str
    route: str | None = None
    confidence: float
    human_summary: str = ""
    action_count: int = 0
    created_at: datetime
    reviewed_at: datetime | None = None


class ProposalDetail(ProposalResponse):
    """Detail-view with full proposal data and action breakdown."""

    actions: list[ProposalAction] = Field(default_factory=list)
    proposal_data: dict[str, Any] = Field(default_factory=dict)
    reviewer: str | None = None


class ProposalEdit(BaseModel):
    """PATCH body for editing a proposal before approving."""

    human_summary: str | None = None
    proposal_data: dict[str, Any] | None = None


class PipelineStatusResponse(BaseModel):
    """Response for checking pipeline status of a capture."""

    capture_id: str
    stage: int
    stage_name: str
    status: Literal["processing", "awaiting_review", "completed", "failed"]
    proposal_id: str | None = None
    error: str | None = None


def build_proposal_actions(proposal_data: dict[str, Any]) -> list[ProposalAction]:
    """Build a list of ProposalAction from raw proposal data."""
    actions: list[ProposalAction] = []

    for node in proposal_data.get("nodes_to_create", []):
        actions.append(ProposalAction(
            action="create_node",
            summary=f"Create {node.get('node_type', 'NODE')} '{node.get('title', '?')}'",
            node_type=node.get("node_type"),
            confidence=node.get("confidence", 0.8),
            impact="low",
        ))

    for update in proposal_data.get("nodes_to_update", []):
        fields = list(update.get("updates", {}).keys())
        actions.append(ProposalAction(
            action="update_node",
            summary=f"Update node {update.get('node_id', '?')}: {', '.join(fields)}",
            confidence=update.get("confidence", 0.8),
            impact="medium",
        ))

    for edge in proposal_data.get("edges_to_create", []):
        actions.append(ProposalAction(
            action="create_edge",
            summary=f"Create {edge.get('edge_type', 'EDGE')} edge",
            edge_type=edge.get("edge_type"),
            confidence=edge.get("confidence", 0.8),
            impact="low",
        ))

    for update in proposal_data.get("edges_to_update", []):
        actions.append(ProposalAction(
            action="update_edge",
            summary=f"Update edge {update.get('edge_id', '?')}",
            confidence=update.get("confidence", 0.8),
            impact="medium",
        ))

    return actions
