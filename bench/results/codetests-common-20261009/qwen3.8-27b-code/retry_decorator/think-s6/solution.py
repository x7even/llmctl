"""Retry decorator factory for flaky function calls."""

from __future__ import annotations

import time
from functools import wraps
from typing import Callable

__all__ = ["retry"]


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """Return a decorator that retries a function with exponential backoff."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if delay < 0:
        raise ValueError("delay must be non-negative")
    if backoff < 1:
        raise ValueError("backoff must be at least 1")

    if isinstance(exceptions, tuple):
        exc_types = exceptions
    elif isinstance(exceptions, type):
        exc_types = (exceptions,)
    else:
        try:
            exc_types = tuple(exceptions)
        except TypeError:
            exc_types = (exceptions,)

    def decorator(func: Callable) -> Callable:
        calls = 0

        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal calls
            for attempt in range(max_attempts):
                calls += 1
                wrapper.calls = calls
                try:
                    return func(*args, **kwargs)
                except exc_types:
                    if attempt == max_attempts - 1:
                        raise
                    sleep(float(delay * (backoff ** attempt)))

        wrapper.calls = 0
        return wrapper

    return decorator
