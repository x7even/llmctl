"""A retry decorator factory for calling flaky functions.

Usage:
    @retry(max_attempts=5, delay=0.5)
    def flaky_function(...):
        ...
"""

from __future__ import annotations

import functools
import time
from typing import Callable


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> Callable:
    """Return a decorator that retries a function on specified exceptions.

    Args:
        max_attempts: Total number of calls to attempt (must be >= 1).
        delay: Base delay in seconds before the first retry (must be >= 0).
        backoff: Multiplier applied to the delay after each retry (must be >= 1).
        exceptions: Tuple of exception types that trigger a retry.
        sleep: Callable used to wait between retries.

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

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                wrapper.calls += 1
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt == max_attempts:
                        raise
                    wait_time = delay * backoff ** (attempt - 1)
                    sleep(wait_time)
            # Should never reach here, but satisfy type checkers.
            raise last_exception  # type: ignore[misc]

        wrapper.calls = 0  # type: ignore[attr-defined]
        return wrapper

    return decorator
