"""Retry decorator factory for calling flaky functions.

Standard library only.
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
    """Return a decorator that transparently retries a function on transient failures.

    Parameters
    ----------
    max_attempts:
        Total number of times the wrapped function may be invoked per call.
    delay:
        Base wait time (seconds) before the first retry.
    backoff:
        Multiplicative factor applied to *delay* on each subsequent retry.
    exceptions:
        Tuple of exception types that trigger a retry.  Anything else
        propagates immediately.
    sleep:
        Callable used to perform the wait (injectable for testing).

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
            for attempt in range(max_attempts):
                try:
                    wrapper.calls += 1
                    return func(*args, **kwargs)
                except exceptions:
                    if attempt == max_attempts - 1:
                        raise  # re-raise the last exception, no further wait
                    sleep(delay * backoff ** attempt)

        wrapper.calls = 0  # type: ignore[attr-defined]
        return wrapper

    return decorator
