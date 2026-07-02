"""Shared async utilities for running coroutines from sync contexts."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging

logger = logging.getLogger(__name__)

# Shared thread pool for running async code from sync contexts.
# Avoids creating/destroying a ThreadPoolExecutor per call.
# Size is configurable via MEMORA_THREAD_POOL_WORKERS or Settings.thread_pool_workers.
_shared_pool: concurrent.futures.ThreadPoolExecutor | None = None


def _get_pool() -> concurrent.futures.ThreadPoolExecutor:
    """Lazily initialize the shared thread pool."""
    global _shared_pool
    if _shared_pool is None:
        try:
            from memora.config import load_settings
            workers = load_settings().thread_pool_workers
        except Exception:
            workers = 8
        _shared_pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    return _shared_pool


def run_async(coro):
    """Run an async coroutine from a sync context, handling nested event loops.

    Uses a shared thread pool instead of creating one per call.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already in an event loop (e.g. FastAPI) — run in a thread
    return _get_pool().submit(asyncio.run, coro).result()
