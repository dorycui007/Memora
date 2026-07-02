"""FastAPI dependency injection for shared resources."""

from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException

from memora.config import Settings
from memora.core.event_bus import EventBus
from memora.graph.repository import GraphRepository
from memora.vector.embeddings import EmbeddingEngine
from memora.vector.store import VectorStore


class AppState:
    """Shared application state initialized during FastAPI lifespan."""

    def __init__(self) -> None:
        self.repo: GraphRepository | None = None
        self.vector_store: VectorStore | None = None
        self.embedding_engine: EmbeddingEngine | None = None
        self.event_bus: EventBus | None = None
        self.settings: Settings | None = None
        self.scheduler: Any = None


# Module-level singleton
app_state = AppState()


def get_repo() -> GraphRepository:
    """FastAPI dependency: get GraphRepository."""
    if app_state.repo is None:
        raise RuntimeError("Repository not initialized")
    return app_state.repo


def get_event_bus() -> EventBus:
    """FastAPI dependency: get EventBus."""
    if app_state.event_bus is None:
        raise RuntimeError("EventBus not initialized")
    return app_state.event_bus


def get_settings() -> Settings:
    """FastAPI dependency: get Settings."""
    if app_state.settings is None:
        raise RuntimeError("Settings not initialized")
    return app_state.settings


async def verify_api_key(authorization: str | None = Header(default=None)) -> None:
    """Verify API key if one is configured. No-op when api_key is empty."""
    if app_state.settings is None:
        raise RuntimeError("Settings not initialized")
    api_key = app_state.settings.api_key
    if not api_key:
        return  # No key configured — auth disabled
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    # Accept "Bearer <key>" or raw key
    token = authorization.removeprefix("Bearer ").strip()
    if token != api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


def get_vector_store() -> VectorStore | None:
    """FastAPI dependency: get VectorStore (may be None)."""
    return app_state.vector_store


def get_embedding_engine() -> EmbeddingEngine | None:
    """FastAPI dependency: get EmbeddingEngine (may be None)."""
    return app_state.embedding_engine
