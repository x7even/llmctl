"""A retry decorator factory for calling flaky functions."""

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
    """Return a decorator that retries the wrapped function on specified exceptions.

    Must be used with parentheses, e.g. ``@retry()`` or ``@retry(max_attempts=5)``.

    Parameters
    ----------
    max_attempts:
        Total number of calls to attempt (including the first).
    delay:
        Base wait time in seconds before the first retry.
    backoff:
        Multiplicative factor applied to *delay* for each successive retry.
    exceptions:
        Tuple of exception types that should trigger a retry.
    sleep:
        Callable used to sleep between retries (injectable for testing).

    Raises
    ------
    ValueError
        If *max_attempts* < 1, *delay* < 0, or *backoff* < 1.
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
            for attempt in range(max_attempts):
                wrapper.calls += 1
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    # No wait after the final attempt.
                    if attempt < max_attempts - 1:
                        wait_time = delay * backoff ** attempt
                        sleep(wait_time)
            # All attempts exhausted – re-raise the last exception.
            raise last_exception  # type: ignore[misc]

        wrapper.calls = 0  # type: ignore[attr-defined]
        return wrapper

    return decorator
