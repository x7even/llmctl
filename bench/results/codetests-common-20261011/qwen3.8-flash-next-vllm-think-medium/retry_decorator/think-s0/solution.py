"""A retry decorator factory for calling flaky functions."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> Callable:
    """Return a decorator that retries a function on specified exceptions.

    Args:
        max_attempts: Total number of calls allowed (must be >= 1).
        delay: Base delay in seconds before the first retry (must be >= 0).
        backoff: Multiplicative factor for each subsequent wait (must be >= 1).
        exceptions: Tuple of exception types that trigger a retry.
        sleep: Callable used to sleep between retries.

    Returns:
        A decorator that wraps a function with retry logic.

    Raises:
        ValueError: If max_attempts < 1, delay < 0, or backoff < 1.
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")
    if delay < 0:
        raise ValueError(f"delay must be >= 0, got {delay}")
    if backoff < 1:
        raise ValueError(f"backoff must be >= 1, got {backoff}")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(1, max_attempts + 1):
                wrapper.calls += 1  # type: ignore[attr-defined]
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    if attempt == max_attempts:
                        raise
                    wait = delay * backoff ** (attempt - 1)
                    sleep(wait)

        wrapper.calls = 0  # type: ignore[attr-defined]
        return wrapper

    return decorator
