"""FastAPI server — primary interface for Memora 2.0.

Boots the API server with all dependencies, background scheduler,
event bus, and static dashboard files.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from memora.api.deps import app_state, verify_api_key
from memora.config import init_data_directory, load_settings
from memora.core.event_bus import EventBus
from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)

DASHBOARD_DIR = Path(__file__).resolve().parent.parent.parent / "dashboard"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and tear down all application resources."""
    logger.info("Memora server starting up...")

    # Load settings
    settings = load_settings()
    init_data_directory(settings)
    app_state.settings = settings

    # Initialize repository
    repo = GraphRepository(settings.db_path)
    app_state.repo = repo

    # Initialize event bus
    event_bus = EventBus(db_conn=repo.get_truth_layer_conn())
    app_state.event_bus = event_bus
    await event_bus.start()

    # Initialize vector store and embedding engine (lazy, may fail)
    try:
        from memora.vector.embeddings import EmbeddingEngine
        from memora.vector.store import VectorStore

        app_state.embedding_engine = EmbeddingEngine(
            model_name=settings.embedding_model,
            models_dir=settings.models_dir,
        )
        app_state.vector_store = VectorStore(db_path=settings.vector_dir)
        logger.info("Vector store and embedding engine initialized")
    except Exception:
        logger.warning("Vector store initialization failed, semantic search unavailable", exc_info=True)

    # Initialize scheduler
    try:
        from memora.scheduler.scheduler import MemoraScheduler

        scheduler = MemoraScheduler(
            repo=repo,
            app_state=app_state,
            vector_store=app_state.vector_store,
            embedding_engine=app_state.embedding_engine,
            settings=settings,
        )
        scheduler.start()
        app_state.scheduler = scheduler
        logger.info("Scheduler started")
    except Exception:
        logger.warning("Scheduler initialization failed", exc_info=True)

    logger.info("Memora server ready at http://%s:%d", settings.api_host, settings.api_port)

    yield

    # Shutdown
    logger.info("Memora server shutting down...")
    await event_bus.stop()
    if app_state.scheduler:
        app_state.scheduler.shutdown()
    if app_state.vector_store:
        app_state.vector_store.close()
    repo.close()
    logger.info("Memora server stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Memora",
        description="Personal Strategic Intelligence Platform",
        version="2.0.0",
        lifespan=lifespan,
        dependencies=[Depends(verify_api_key)],
    )

    # CORS — restricted to configured origins
    settings = load_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    from memora.api.routes import (
        capture,
        entities,
        edges,
        search,
        investigation,
        timeline,
        people,
        briefing,
        positions,
        academic,
        deadlines,
        patterns,
        health,
        ontology,
        events,
        graph_export,
    )

    app.include_router(capture.router, prefix="/api", tags=["capture"])
    app.include_router(entities.router, prefix="/api", tags=["entities"])
    app.include_router(edges.router, prefix="/api", tags=["edges"])
    app.include_router(search.router, prefix="/api", tags=["search"])
    app.include_router(investigation.router, prefix="/api", tags=["investigation"])
    app.include_router(timeline.router, prefix="/api", tags=["timeline"])
    app.include_router(people.router, prefix="/api", tags=["people"])
    app.include_router(briefing.router, prefix="/api", tags=["briefing"])
    app.include_router(positions.router, prefix="/api", tags=["positions"])
    app.include_router(academic.router, prefix="/api", tags=["academic"])
    app.include_router(deadlines.router, prefix="/api", tags=["deadlines"])
    app.include_router(patterns.router, prefix="/api", tags=["patterns"])
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(ontology.router, prefix="/api", tags=["ontology"])
    app.include_router(events.router, prefix="/api", tags=["events"])
    app.include_router(graph_export.router, prefix="/api", tags=["graph"])

    # Mount dashboard static files
    if DASHBOARD_DIR.exists():
        app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")

    return app


app = create_app()
