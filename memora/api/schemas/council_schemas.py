"""Pydantic schemas for the Council API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QueryType(str, Enum):
    CAPTURE = "capture"
    ANALYSIS = "analysis"
    RESEARCH = "research"
    COUNCIL = "council"


class AgentRole(str, Enum):
    ARCHIVIST = "archivist"
    STRATEGIST = "strategist"
    RESEARCHER = "researcher"
    ORCHESTRATOR = "orchestrator"


# ---- Request schemas ----


class CouncilQueryRequest(BaseModel):
    """Request to submit a query to the AI council."""

    query: str = Field(..., min_length=1, max_length=10000)
    query_type: QueryType | None = None  # auto-classified if None
    context: dict[str, Any] = Field(default_factory=dict)
    max_deliberation_rounds: int = Field(default=2, ge=1, le=5)


class CritiqueRequest(BaseModel):
    """Request to invoke critic mode on a statement/decision."""

    statement: str = Field(..., min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


# ---- Response schemas ----


class AgentOutput(BaseModel):
    """Output from a single agent in the council."""

    agent: AgentRole
    content: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    citations: list[str] = Field(default_factory=list)  # node IDs
    sources: list[dict[str, Any]] = Field(default_factory=list)


class CouncilQueryResponse(BaseModel):
    """Response from the AI council."""

    query_id: str
    query_type: QueryType
    synthesis: str
    agent_outputs: list[AgentOutput] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    citations: list[str] = Field(default_factory=list)
    deliberation_rounds: int = 0
    high_disagreement: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BriefingSectionResponse(BaseModel):
    """A single section of the daily briefing."""

    title: str
    items: list[str] = Field(default_factory=list)
    priority: str = "medium"


class DailyBriefingResponse(BaseModel):
    """Response for the daily briefing endpoint."""

    sections: list[BriefingSectionResponse] = Field(default_factory=list)
    summary: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cached: bool = False


class CritiqueResponse(BaseModel):
    """Response from critic mode."""

    original_statement: str
    critique: str
    counter_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    citations: list[str] = Field(default_factory=list)


# ---- Streaming schemas ----


class StreamToken(BaseModel):
    """A single token in the streaming response."""

    token: str
    agent: AgentRole | None = None
    confidence: float | None = None
    citing_nodes: list[str] = Field(default_factory=list)


class AgentStateUpdate(BaseModel):
    """Update about which agent is currently active."""

    agent: AgentRole
    state: str  # "thinking", "active", "done", "error"
    message: str = ""


class SSEEvent(BaseModel):
    """Server-Sent Event payload."""

    event_type: str  # proposal_created, health_changed, bridge_discovered, etc.
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
