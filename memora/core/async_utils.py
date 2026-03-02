"""Shared async utilities for running coroutines from sync contexts."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging

logger = logging.getLogger(__name__)

# Shared thread pool for running async code from sync contexts.
# Avoids creating/destroying a ThreadPoolExecutor per call.
_shared_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def run_async(coro):
    """Run an async coroutine from a sync context, handling nested event loops.

    Uses a shared thread pool instead of creating one per call.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already in an event loop (e.g. FastAPI) — run in a thread
    return _shared_pool.submit(asyncio.run, coro).result()
