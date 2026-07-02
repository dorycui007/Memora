"""Global rate limiter for OpenAI API calls.

Provides a shared async rate limiter to prevent burst traffic across
multiple agents and background jobs that call the OpenAI API concurrently.
"""

from __future__ import annotations

import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class TokenBucketLimiter:
    """Simple async token-bucket rate limiter.

    Allows up to `rate` requests per `period` seconds, with a burst
    capacity equal to `rate`.
    """

    def __init__(self, rate: int = 60, period: float = 60.0) -> None:
        self._rate = rate
        self._period = period
        self._tokens = float(rate)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available, then consume one."""
        async with self._lock:
            self._refill()
            while self._tokens < 1.0:
                wait = (1.0 - self._tokens) * (self._period / self._rate)
                await asyncio.sleep(wait)
                self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self._rate),
            self._tokens + elapsed * (self._rate / self._period),
        )
        self._last_refill = now


# Shared global limiter instance (60 RPM default for gpt-5-nano)
_global_limiter: TokenBucketLimiter | None = None


def get_global_limiter(rate: int = 60, period: float = 60.0) -> TokenBucketLimiter:
    """Get or create the shared global rate limiter."""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = TokenBucketLimiter(rate=rate, period=period)
    return _global_limiter
