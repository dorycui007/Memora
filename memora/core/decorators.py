"""Reusable decorators for Memora.

Provides common patterns like safe execution with logging
and lazy property initialization.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def safe_run(
    default: Any = None,
    logger: logging.Logger | None = None,
    message: str = "",
) -> Callable:
    """Decorator that catches exceptions and returns a default value.

    Replaces the repeated pattern of:
        try:
            return some_operation()
        except Exception:
            logger.warning("...", exc_info=True)
            return []

    Usage:
        @safe_run(default=[], logger=logger)
        def detect_something(self):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception:
                log = logger or logging.getLogger(func.__module__)
                msg = message or f"{func.__qualname__} failed"
                log.warning(msg, exc_info=True)
                # Return a copy of mutable defaults to avoid shared state
                if isinstance(default, (list, dict, set)):
                    return type(default)()
                return default
        return wrapper  # type: ignore[return-value]
    return decorator


class lazy_property:  # noqa: N801 — lowercase to match @property convention
    """Descriptor for lazy-initialized properties.

    Replaces the repeated pattern of:
        def _get_thing(self):
            if self._thing is not None:
                return self._thing
            self._thing = ExpensiveThing()
            return self._thing

    Usage:
        class MyClass:
            @lazy_property
            def expensive_thing(self) -> Thing:
                return Thing(...)
    """

    def __init__(self, func: Callable[..., T]) -> None:
        self._func = func
        self._attr_name = f"_lazy_{func.__name__}"
        self.__doc__ = func.__doc__

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr_name = f"_lazy_{name}"

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        val = getattr(obj, self._attr_name, None)
        if val is None:
            val = self._func(obj)
            setattr(obj, self._attr_name, val)
        return val
