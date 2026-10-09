import functools
import time
from typing import Callable, Tuple, Type


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> Callable:
    """
    A decorator factory for retrying flaky functions.

    Args:
        max_attempts: Maximum number of attempts to call the function.
        delay: Initial delay between retries in seconds.
        backoff: Multiplier for the delay after each retry.
        exceptions: Tuple of exception types to catch and retry on.
        sleep: Function to call for sleeping, defaults to time.sleep.

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
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            wrapper.calls += 1
            attempt = 0
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        wait_time = delay * (backoff ** (attempt - 1))
                        sleep(wait_time)
            # All attempts failed, re-raise the last exception
            raise last_exception

        wrapper.calls = 0
        return wrapper

    return decorator
