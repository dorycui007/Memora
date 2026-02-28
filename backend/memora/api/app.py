"""FastAPI application factory and main entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from memora.config import load_settings
from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler — initialize DB connections on startup."""
    settings = load_settings()
    logger.info("Starting Memora API (data_dir=%s)", settings.data_dir)

    # Initialize graph repository
    repo = GraphRepository(db_path=settings.db_path)
    app.state.repo = repo
    app.state.settings = settings

    # Enable WAL mode for crash recovery
    try:
        from memora.core.backup import BackupManager
        BackupManager.enable_wal_mode(repo._conn)
    except Exception:
        logger.debug("WAL mode setup skipped")

    # Vector store (lazy — initialized when first needed)
    app.state.vector_store = None

    # Embedding engine (lazy — initialized when first needed)
    app.state.embedding_engine = None

    # Truth layer (lazy — initialized when first needed)
    app.state.truth_layer = None

    # Pipeline (lazy — initialized when first needed)
    app.state.pipeline = None

    # Orchestrator (lazy — initialized when first needed by council routes)
    app.state.orchestrator = None
    app.state.strategist = None

    # Background scheduler
    scheduler = None
    try:
        from memora.scheduler.scheduler import MemoraScheduler

        scheduler = MemoraScheduler(
            repo=repo,
            vector_store=app.state.vector_store,
            embedding_engine=app.state.embedding_engine,
            truth_layer=app.state.truth_layer,
            settings=settings,
        )
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("Background scheduler started")
    except Exception:
        logger.warning("Failed to start background scheduler", exc_info=True)
        app.state.scheduler = None

    yield

    # Shutdown
    if scheduler:
        scheduler.shutdown()
    repo.close()
    logger.info("Memora API shut down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Memora API",
        version="0.1.0",
        description="Decision intelligence platform API",
        lifespan=lifespan,
    )

    # CORS restricted to localhost origins only (security)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check
    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    # Register route routers
    from memora.api.routes.captures import router as captures_router
    from memora.api.routes.council import router as council_router
    from memora.api.routes.facts import router as facts_router
    from memora.api.routes.graph import router as graph_router
    from memora.api.routes.networks import router as networks_router
    from memora.api.routes.proposals import router as proposals_router

    app.include_router(captures_router)
    app.include_router(graph_router)
    app.include_router(proposals_router)
    app.include_router(facts_router)
    app.include_router(council_router)
    app.include_router(networks_router)

    return app


# Default app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "memora.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
