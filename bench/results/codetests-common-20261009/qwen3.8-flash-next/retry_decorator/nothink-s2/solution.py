import functools
import time
from typing import Callable, TypeVar, Any

T = TypeVar('T')


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """
    A decorator factory for retrying flaky functions.
    
    Args:
        max_attempts: Maximum number of attempts (must be >= 1).
        delay: Initial delay in seconds before the first retry (must be >= 0).
        backoff: Multiplier for the delay on each subsequent retry (must be >= 1).
        exceptions: Tuple of exception types to catch and retry on.
        sleep: Function to call for sleeping (defaults to time.sleep).
    
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

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    wrapper.calls += 1
                    return result
                except exceptions as e:
                    wrapper.calls += 1
                    last_exception = e
                    if attempt < max_attempts:
                        sleep_time = delay * (backoff ** (attempt - 1))
                        sleep(sleep_time)
                # If exception is not in exceptions, it propagates immediately
            # All attempts failed, re-raise the last exception
            raise last_exception
        wrapper.calls = 0
        return wrapper
    return decorator
