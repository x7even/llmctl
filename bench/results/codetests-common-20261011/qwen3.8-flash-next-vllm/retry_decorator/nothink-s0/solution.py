import functools
import time
from typing import Callable, TypeVar, Any

T = TypeVar('T')


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep
) -> Callable:
    """
    A decorator factory for retrying flaky functions.
    
    Args:
        max_attempts: Maximum number of attempts (must be >= 1).
        delay: Initial delay in seconds before the first retry (must be >= 0).
        backoff: Multiplier for the delay after each retry (must be >= 1).
        exceptions: Tuple of exception types to catch and retry on.
        sleep: Function to call for sleeping, defaults to time.sleep.
    
    Returns:
        A decorator that wraps a function with retry logic.
    
    Raises:
        ValueError: If max_attempts < 1, delay < 0, or backoff < 1.
    """
    # Validate parameters at retry() call time
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if delay < 0:
        raise ValueError("delay must be >= 0")
    if backoff < 1:
        raise ValueError("backoff must be >= 1")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Initialize calls counter if not present
            if not hasattr(wrapper, 'calls'):
                wrapper.calls = 0
            
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                wrapper.calls += 1
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    # If this was the last attempt, don't sleep
                    if attempt < max_attempts:
                        # Calculate delay for this retry
                        # Retry number k = attempt (since attempt 1 failed, we're doing retry 1)
                        # Wait = delay * backoff ** (k - 1)
                        # For attempt 1 (first failure), k=1, wait = delay * backoff^0 = delay
                        # For attempt 2 (second failure), k=2, wait = delay * backoff^1
                        wait_time = delay * (backoff ** (attempt - 1))
                        sleep(wait_time)
            
            # All attempts failed, re-raise the last exception
            raise last_exception
        
        # Initialize calls attribute on the wrapper
        wrapper.calls = 0
        
        return wrapper
    
    return decorator
