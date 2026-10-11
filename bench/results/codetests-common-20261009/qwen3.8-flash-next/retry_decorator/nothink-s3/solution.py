import time
import functools
from typing import Callable


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """
    A decorator factory for retrying flaky functions.
    
    Args:
        max_attempts: Maximum number of attempts (must be >= 1).
        delay: Initial delay in seconds before the first retry (must be >= 0).
        backoff: Multiplicative factor for the delay after each retry (must be >= 1).
        exceptions: Tuple of exception types to catch and retry on.
        sleep: Function to call for sleeping (defaults to time.sleep).
    
    Returns:
        A decorator that wraps a function with retry logic.
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
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    return result
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        # Wait before the next retry
                        wait_time = delay * (backoff ** (attempt - 1))
                        sleep(wait_time)
                        wrapper.calls += 1
                    else:
                        # Final attempt failed, raise the exception
                        raise last_exception
            # This should not be reached, but just in case
            raise last_exception
        
        wrapper.calls = 0
        return wrapper
    
    return decorator
