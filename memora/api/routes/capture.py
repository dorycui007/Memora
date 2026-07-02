"""Capture route — ingest text through the extraction pipeline."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from memora.api.deps import get_event_bus, get_repo, get_settings, get_vector_store, get_embedding_engine
from memora.core.event_bus import EventBus
from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)
router = APIRouter()


class CaptureRequest(BaseModel):
    text: str
    metadata: dict | None = None


class CaptureResponse(BaseModel):
    capture_id: str
    status: str
    message: str
    nodes_created: int = 0
    warnings: list[str] = []


@router.post("/capture", response_model=CaptureResponse)
async def capture_text(
    request: CaptureRequest,
    repo: GraphRepository = Depends(get_repo),
    event_bus: EventBus = Depends(get_event_bus),
    settings=Depends(get_settings),
    vector_store=Depends(get_vector_store),
    embedding_engine=Depends(get_embedding_engine),
):
    """Ingest text through the 9-stage extraction pipeline."""
    from memora.core.pipeline import ExtractionPipeline
    from memora.graph.models import Capture

    capture_id = str(uuid4())
    capture = Capture(
        id=capture_id,
        raw_content=request.text,
        metadata=request.metadata or {},
    )
    capture.compute_content_hash()

    # Check for duplicates
    if repo.check_capture_exists(capture.content_hash):
        return CaptureResponse(
            capture_id=capture_id,
            status="duplicate",
            message="This content has already been captured.",
        )

    repo.create_capture(capture)

    pipeline = ExtractionPipeline(
        repo=repo,
        vector_store=vector_store,
        embedding_engine=embedding_engine,
        settings=settings,
    )

    state = await pipeline.run(capture_id, request.text)

    # Publish event
    if state.status == "completed":
        await event_bus.publish(
            "capture.completed",
            {"capture_id": capture_id, "nodes_created": len(state.proposal.nodes_to_create) if state.proposal else 0},
            source="pipeline",
        )

    return CaptureResponse(
        capture_id=capture_id,
        status=state.status,
        message=state.error or "Capture processed successfully.",
        nodes_created=len(state.proposal.nodes_to_create) if state.proposal else 0,
        warnings=state.warnings,
    )
