"""Capture API routes — POST /captures for text ingestion with pipeline trigger."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from memora.api.schemas.capture_schemas import CaptureCreate, CaptureResponse
from memora.graph.models import Capture

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/captures", tags=["captures"])


def _get_pipeline(request: Request):
    """Get or lazily initialize the extraction pipeline."""
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        settings = getattr(request.app.state, "settings", None)
        if settings and settings.openai_api_key:
            try:
                from memora.core.pipeline import ExtractionPipeline
                from memora.vector.embeddings import EmbeddingEngine
                from memora.vector.store import VectorStore

                # Initialize dependencies
                vector_store = getattr(request.app.state, "vector_store", None)
                embedding_engine = getattr(request.app.state, "embedding_engine", None)

                if vector_store is None:
                    vector_store = VectorStore(db_path=settings.vector_dir)
                    request.app.state.vector_store = vector_store

                if embedding_engine is None:
                    embedding_engine = EmbeddingEngine(
                        model_name=settings.embedding_model,
                        cache_dir=settings.models_dir,
                    )
                    request.app.state.embedding_engine = embedding_engine

                pipeline = ExtractionPipeline(
                    repo=request.app.state.repo,
                    vector_store=vector_store,
                    embedding_engine=embedding_engine,
                    settings=settings,
                )
                request.app.state.pipeline = pipeline
            except Exception:
                logger.warning("Failed to initialize pipeline", exc_info=True)
    return pipeline


@router.get("")
async def list_captures(request: Request, limit: int = 20, offset: int = 0):
    """List captures, most recent first."""
    repo = request.app.state.repo
    captures = repo.list_captures(limit=limit, offset=offset)
    return [c.model_dump(mode="json") for c in captures]


@router.post("", response_model=CaptureResponse)
async def create_capture(body: CaptureCreate, request: Request) -> CaptureResponse:
    """Accept a text capture, compute hash, check dedup, store, and trigger pipeline."""
    repo = request.app.state.repo

    # Compute content hash for dedup
    content_hash = hashlib.sha256(body.content.encode()).hexdigest()

    if repo.check_capture_exists(content_hash):
        raise HTTPException(status_code=409, detail="Duplicate capture detected")

    capture = Capture(
        modality=body.modality,
        raw_content=body.content,
        content_hash=content_hash,
        metadata=body.metadata,
    )
    capture_id = repo.create_capture(capture)

    # Kick off the extraction pipeline as a background task
    pipeline = _get_pipeline(request)
    if pipeline:
        asyncio.create_task(
            _run_pipeline(pipeline, str(capture_id), body.content)
        )

    return CaptureResponse(
        id=str(capture_id),
        status="processing",
        pipeline_stage=1,
        created_at=capture.created_at,
    )


@router.get("/{capture_id}")
async def get_capture(capture_id: str, request: Request):
    """Retrieve a capture by ID."""
    repo = request.app.state.repo
    capture = repo.get_capture(UUID(capture_id))
    if capture is None:
        raise HTTPException(status_code=404, detail="Capture not found")
    return capture.model_dump(mode="json")


async def _run_pipeline(pipeline, capture_id: str, content: str) -> None:
    """Run the extraction pipeline in the background."""
    try:
        state = await pipeline.run(capture_id, content)
        if state.error:
            logger.error(
                "Pipeline failed for capture %s: %s", capture_id, state.error
            )
        else:
            logger.info(
                "Pipeline completed for capture %s (status=%s, proposal=%s)",
                capture_id, state.status, state.proposal_id,
            )
    except Exception:
        logger.exception("Pipeline crashed for capture %s", capture_id)
