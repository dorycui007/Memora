"""Retry utility with exponential backoff for API calls.

Provides a decorator and helper for retrying transient failures
with configurable backoff, jitter, and error classification.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from functools import wraps
from typing import Any, Callable, TypeVar

import httpx
import openai

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# OpenAI exceptions that are safe to retry
_RETRYABLE_OPENAI = (
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APIConnectionError,
    openai.APITimeoutError,
)

# HTTP exceptions that are safe to retry
_RETRYABLE_HTTP = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.ConnectError,
)


def is_retryable(exc: Exception) -> bool:
    """Return True if the exception is transient and worth retrying."""
    if isinstance(exc, _RETRYABLE_OPENAI):
        return True
    if isinstance(exc, _RETRYABLE_HTTP):
        return True
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
        return True
    return False


def compute_delay(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> float:
    """Compute delay with exponential backoff and jitter.

    Uses full jitter: uniform random between 0 and the exponential cap.
    """
    exp_delay = min(base_delay * (2 ** attempt), max_delay)
    return random.uniform(0, exp_delay)


def retry_on_transient(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Callable[[F], F]:
    """Decorator that retries a function on transient API errors.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds for exponential backoff.
        max_delay: Maximum delay in seconds between retries.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt >= max_retries or not is_retryable(exc):
                        raise
                    delay = compute_delay(attempt, base_delay, max_delay)
                    logger.warning(
                        "Retryable error in %s (attempt %d/%d), retrying in %.1fs: %s",
                        func.__qualname__,
                        attempt + 1,
                        max_retries,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
            raise last_exc  # type: ignore[misc]  # unreachable

        return wrapper  # type: ignore[return-value]

    return decorator


def call_with_retry(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    **kwargs: Any,
) -> Any:
    """Call a function with retry logic (non-decorator form).

    Args:
        func: The function to call.
        *args: Positional arguments for the function.
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds for exponential backoff.
        max_delay: Maximum delay in seconds between retries.
        **kwargs: Keyword arguments for the function.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_retries or not is_retryable(exc):
                raise
            delay = compute_delay(attempt, base_delay, max_delay)
            logger.warning(
                "Retryable error in %s (attempt %d/%d), retrying in %.1fs: %s",
                func.__qualname__ if hasattr(func, "__qualname__") else str(func),
                attempt + 1,
                max_retries,
                delay,
                exc,
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]  # unreachable


async def async_call_with_retry(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    **kwargs: Any,
) -> Any:
    """Async version of call_with_retry — uses asyncio.sleep instead of time.sleep.

    Args:
        func: The async function to call.
        *args: Positional arguments for the function.
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds for exponential backoff.
        max_delay: Maximum delay in seconds between retries.
        **kwargs: Keyword arguments for the function.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_retries or not is_retryable(exc):
                raise
            delay = compute_delay(attempt, base_delay, max_delay)
            logger.warning(
                "Retryable error in %s (attempt %d/%d), retrying in %.1fs: %s",
                func.__qualname__ if hasattr(func, "__qualname__") else str(func),
                attempt + 1,
                max_retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]  # unreachable
