import time
from functools import wraps
from typing import Callable

__all__ = ["retry"]


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """Return a decorator that retries a flaky function with backoff."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if delay < 0:
        raise ValueError("delay must be non-negative")
    if backoff < 1:
        raise ValueError("backoff must be at least 1")

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                wrapper.calls += 1
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    if attempt == max_attempts:
                        raise
                    sleep(delay * (backoff ** (attempt - 1)))

        wrapper.calls = 0
        return wrapper

    return decorator
