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
    A decorator factory that retries a function on specified exceptions.
    
    Args:
        max_attempts: Maximum number of attempts (must be >= 1).
        delay: Initial delay between retries in seconds (must be >= 0).
        backoff: Multiplicative factor for delay between retries (must be >= 1).
        exceptions: Tuple of exception types to catch and retry on.
        sleep: Function to sleep for a given number of seconds.
    
    Returns:
        A decorator that wraps a function with retry logic.
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
                wrapper.calls += 1
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        wait_time = delay * (backoff ** (attempt - 1))
                        sleep(wait_time)
                    else:
                        # Last attempt failed, re-raise
                        raise
                # If exception is not in exceptions, it propagates immediately
            # This line should never be reached if max_attempts >= 1
            raise last_exception  # pragma: no cover

        wrapper.calls = 0
        return wrapper

    return decorator
