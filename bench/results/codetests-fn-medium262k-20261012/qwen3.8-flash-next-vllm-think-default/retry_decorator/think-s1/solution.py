"""Retry decorator factory for calling flaky functions."""

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
    max_attempts : int
        Maximum number of times to call the function (including the first call).
    delay : float
        Base delay in seconds before the first retry.
    backoff : float
        Multiplier applied to the delay after each successive failure.
    exceptions : tuple of exception types
        Exception types that trigger a retry.
    sleep : callable
        Function used to sleep between retries (injectable for testing).

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
            for attempt in range(1, max_attempts + 1):
                wrapper.calls += 1
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    if attempt == max_attempts:
                        raise
                    wait_time = delay * backoff ** (attempt - 1)
                    sleep(wait_time)

        wrapper.calls = 0
        return wrapper

    return decorator
