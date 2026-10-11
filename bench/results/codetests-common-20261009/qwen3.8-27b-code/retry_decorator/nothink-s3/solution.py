"""A retry decorator factory for calling flaky functions."""

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
    """
    Create a decorator that retries a flaky function.

    Args:
        max_attempts: Maximum number of times to call the function.
        delay: Initial delay in seconds before the first retry.
        backoff: Multiplier for the delay after each subsequent failure.
        exceptions: Tuple of exception types to catch and retry.
        sleep: Function to call for sleeping.

    Returns:
        A decorator that wraps a function with retry logic.

    Raises:
        ValueError: If max_attempts < 1, delay < 0, or backoff < 1.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if delay < 0:
        raise ValueError("delay must be >= 0")
    if backoff < 1:
        raise ValueError("backoff must be >= 1")

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
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
                        wait = delay * (backoff ** (attempt - 1))
                        sleep(wait)
            raise last_exception

        wrapper.calls = 0
        return wrapper

    return decorator
