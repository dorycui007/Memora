"""API schemas for capture endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CaptureCreate(BaseModel):
    """Request body for creating a new capture."""

    modality: Literal["text"] = "text"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaptureResponse(BaseModel):
    """Response after creating a capture."""

    id: str
    status: str = "processing"
    pipeline_stage: int = 1
    created_at: datetime


class CaptureDetail(BaseModel):
    """Full capture with linked proposal info."""

    id: str
    modality: Literal["text"] = "text"
    raw_content: str
    processed_content: str
    content_hash: str
    language: str
    metadata: dict[str, Any]
    created_at: datetime
    proposals: list[dict[str, Any]] = Field(default_factory=list)
