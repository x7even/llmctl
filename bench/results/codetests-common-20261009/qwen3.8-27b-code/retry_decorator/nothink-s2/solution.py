import time
import functools
from typing import Callable, Any


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """Decorator factory that retries a flaky function up to max_attempts times."""
    # Validate parameters
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if delay < 0:
        raise ValueError("delay must be >= 0")
    if backoff < 1:
        raise ValueError("backoff must be >= 1")

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Track total calls across all invocations of the wrapper
            wrapper.calls += 1

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        # Last attempt failed, re-raise
                        raise
                    # Wait before retry number k (k = attempt, since attempt is the
                    # number of the failed attempt, and the next retry is attempt+1)
                    # Wait before retry number k: delay * backoff ** (k - 1)
                    # Here, k = attempt (the retry that follows this failure)
                    wait_time = delay * (backoff ** (attempt - 1))
                    sleep(wait_time)
            # This should never be reached, but just in case
            raise RuntimeError("Unreachable")

        wrapper.calls = 0
        return wrapper

    return decorator
