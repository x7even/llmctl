import functools
import time
from typing import Callable, TypeVar, Any

F = TypeVar('F', bound=Callable[..., Any])


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep
) -> Callable[[F], F]:
    """
    A decorator factory that retries a function call on specified exceptions.
    
    Args:
        max_attempts: Maximum number of attempts (including the first call).
        delay: Initial delay in seconds before the first retry.
        backoff: Multiplier for the delay after each retry.
        exceptions: Tuple of exception types to catch and retry on.
        sleep: Function to call to sleep for a given number of seconds.
    
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
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    result = func(*args, **kwargs)
                    wrapper.calls += 1
                    return result
                except exceptions as e:
                    last_exception = e
                    wrapper.calls += 1
                    # If this was the last attempt, don't sleep
                    if attempt < max_attempts - 1:
                        wait_time = delay * (backoff ** attempt)
                        sleep(wait_time)
            # All attempts failed, re-raise the last exception
            raise last_exception
        
        wrapper.calls = 0
        return wrapper
    
    return decorator
