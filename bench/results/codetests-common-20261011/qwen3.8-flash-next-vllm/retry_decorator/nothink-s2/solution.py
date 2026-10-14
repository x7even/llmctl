import functools
import time
from typing import Callable, TypeVar, Any

T = TypeVar('T')


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """
    A decorator factory that retries a function on specified exceptions.
    
    Args:
        max_attempts: Maximum number of attempts (must be >= 1).
        delay: Initial delay in seconds between retries (must be >= 0).
        backoff: Multiplicative factor for delay between retries (must be >= 1).
        exceptions: Tuple of exception types to catch and retry on.
        sleep: Function to call for sleeping (defaults to time.sleep).
    
    Returns:
        A decorator that wraps a function with retry logic.
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
            last_exception: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    wrapper.calls += 1
                    result = func(*args, **kwargs)
                    return result
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        wait_time = delay * (backoff ** (attempt - 1))
                        sleep(wait_time)
                except BaseException:
                    # An exception not in `exceptions` propagates immediately
                    raise
            # All attempts failed; re-raise the last exception
            if last_exception is not None:
                raise last_exception
            # This should not happen since max_attempts >= 1, but just in case
            raise RuntimeError("No attempts were made")

        wrapper.calls = 0
        return wrapper

    return decorator
