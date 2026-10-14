import time
import functools
from typing import Callable, TypeVar, Any

T = TypeVar('T')


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """
    A decorator factory for retrying flaky functions.
    
    Args:
        max_attempts: Maximum number of attempts (including the first call).
        delay: Initial delay in seconds before the first retry.
        backoff: Multiplicative factor for the delay on each subsequent retry.
        exceptions: Tuple of exception types to catch and retry on.
        sleep: Function to call for sleeping, defaults to time.sleep.
    
    Returns:
        A decorator that wraps a function with retry logic.
    
    Raises:
        ValueError: If max_attempts < 1, delay < 0, or backoff < 1.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if delay < 0:
        raise ValueError("delay must be non-negative")
    if backoff < 1:
        raise ValueError("backoff must be at least 1")
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: BaseException | None = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    wrapper.calls += 1
                    result = func(*args, **kwargs)
                    return result
                except exceptions as e:
                    last_exception = e
                    # If this was the last attempt, don't sleep
                    if attempt < max_attempts:
                        # Calculate wait time for retry number k = attempt
                        # k = 1 for wait after first failure, so k = attempt
                        wait_time = delay * (backoff ** (attempt - 1))
                        sleep(wait_time)
            
            # All attempts failed, re-raise the last exception
            if last_exception is not None:
                raise last_exception
            # This should never happen since max_attempts >= 1
            raise RuntimeError("No attempts were made")
        
        # Initialize the calls counter
        wrapper.calls = 0
        
        return wrapper
    
    return decorator
