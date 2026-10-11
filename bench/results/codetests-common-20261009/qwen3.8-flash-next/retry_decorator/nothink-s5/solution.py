import functools
import time
from typing import Callable, TypeVar, Any

F = TypeVar('F', bound=Callable[..., Any])


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """
    A decorator factory for retrying flaky functions.
    
    Args:
        max_attempts: Maximum number of attempts (must be >= 1).
        delay: Initial delay in seconds before the first retry (must be >= 0).
        backoff: Multiplier for the delay after each retry (must be >= 1).
        exceptions: Tuple of exception types to catch and retry on.
        sleep: Function to call for sleeping, takes a float number of seconds.
    
    Returns:
        A decorator that wraps a function with retry logic.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if delay < 0:
        raise ValueError("delay must be non-negative")
    if backoff < 1:
        raise ValueError("backoff must be at least 1")

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            wrapper.calls += 1
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        # Calculate delay for this retry
                        # For retry number k (1-indexed), delay = delay * backoff ** (k - 1)
                        # attempt is the current attempt number (1-indexed)
                        # The wait after attempt `attempt` is for retry k = attempt
                        k = attempt
                        wait_time = delay * (backoff ** (k - 1))
                        sleep(wait_time)
                        wrapper.calls += 1
                    else:
                        # Last attempt failed, re-raise
                        raise
                except BaseException:
                    # Non-matching exception, propagate immediately
                    raise
            # This should never be reached because we either return or raise in the loop
            raise last_exception  # pragma: no cover
        wrapper.calls = 0
        return wrapper
    return decorator
