import time
import functools
from typing import Callable


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """
    A decorator factory that retries a function call if it raises specified exceptions.
    
    Args:
        max_attempts: Maximum number of attempts (must be >= 1).
        delay: Initial delay between retries in seconds (must be >= 0).
        backoff: Multiplier for the delay after each retry (must be >= 1).
        exceptions: Tuple of exception types to catch and retry on.
        sleep: Function to call for sleeping between retries.
    
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
                    wrapper.calls += 1
                    result = func(*args, **kwargs)
                    return result
                except exceptions as e:
                    last_exception = e
                    # If this was the last attempt, don't sleep
                    if attempt < max_attempts:
                        # Calculate delay for this retry
                        # retry number k = attempt (since attempt 1 failed, we're about to do retry 1)
                        # k = attempt, so delay * backoff ** (k - 1) = delay * backoff ** (attempt - 1)
                        current_delay = delay * (backoff ** (attempt - 1))
                        sleep(current_delay)
                except BaseException:
                    # Non-matching exception propagates immediately
                    raise
            # All attempts failed, re-raise the last exception
            raise last_exception
        
        wrapper.calls = 0
        return wrapper
    
    return decorator
