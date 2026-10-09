"""A retry decorator factory for calling flaky functions."""

from functools import wraps
from typing import Callable
import time


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> Callable:
    """
    A decorator factory that retries a function on specified exceptions.

    Args:
        max_attempts: Maximum number of attempts to call the function.
        delay: Initial delay in seconds before the first retry.
        backoff: Multiplier for the delay after each retry.
        exceptions: Tuple of exception types that should trigger a retry.
        sleep: Callable to use for sleeping (defaults to time.sleep).

    Returns:
        A decorator that wraps the function with retry logic.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if delay < 0:
        raise ValueError("delay must be non-negative")
    if backoff < 1:
        raise ValueError("backoff must be at least 1")

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    wrapper.calls += 1
                    return result
                except exceptions as e:
                    last_exception = e
                    wrapper.calls += 1
                    if attempt < max_attempts:
                        wait_time = delay * (backoff ** (attempt - 1))
                        sleep(wait_time)
            raise last_exception

        wrapper.calls = 0
        return wrapper

    return decorator
