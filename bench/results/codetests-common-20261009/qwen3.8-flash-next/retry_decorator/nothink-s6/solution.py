import functools
import time
from typing import Callable


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """
    A decorator factory for retrying flaky functions.
    
    Parameters:
    - max_attempts: Maximum number of attempts (including the first call).
    - delay: Initial delay in seconds before the first retry.
    - backoff: Multiplicative factor for the delay on each subsequent retry.
    - exceptions: Tuple of exception types to catch and retry on.
    - sleep: Function to use for sleeping (defaults to time.sleep).
    
    Returns:
    - A decorator that wraps a function with retry logic.
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
                except BaseException:
                    wrapper.calls += 1
                    raise
            # All attempts failed
            raise last_exception

        wrapper.calls = 0
        return wrapper

    return decorator
