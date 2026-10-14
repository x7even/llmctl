"""A retry decorator factory for calling flaky functions.

Standard-library-only implementation.
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

    Parameters
    ----------
    max_attempts:
        Total number of times the wrapped function may be called.
    delay:
        Base delay (seconds) before the first retry.
    backoff:
        Multiplicative factor applied to *delay* for each subsequent retry.
    exceptions:
        Tuple of exception types that trigger a retry.
    sleep:
        Callable used to wait between retries (injectable for testing).

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

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc: BaseException | None = None
            for attempt in range(max_attempts):
                wrapper.calls += 1
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    # Wait only if this was not the final attempt.
                    if attempt < max_attempts - 1:
                        sleep(delay * backoff ** attempt)
            # All attempts exhausted – re-raise the last caught exception.
            raise last_exc  # type: ignore[misc]

        wrapper.calls = 0
        return wrapper

    return decorator
