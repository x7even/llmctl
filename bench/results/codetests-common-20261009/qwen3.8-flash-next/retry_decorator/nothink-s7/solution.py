import functools
import time
from typing import Callable


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """
    A decorator factory for retrying flaky functions.
    
    Args:
        max_attempts: Maximum number of attempts (must be >= 1).
        delay: Initial delay between retries in seconds (must be >= 0).
        backoff: Multiplier for delay on each retry (must be >= 1).
        exceptions: Tuple of exception types to catch and retry.
        sleep: Function to use for sleeping (default: time.sleep).
    
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
            wrapper.calls += 1
            attempt = 0
            while True:
                attempt += 1
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt >= max_attempts:
                        raise
                    wait_time = delay * (backoff ** (attempt - 1))
                    sleep(wait_time)
                    wrapper.calls += 1
        wrapper.calls = 0
        return wrapper
    return decorator
