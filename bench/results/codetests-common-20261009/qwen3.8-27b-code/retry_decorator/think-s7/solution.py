from __future__ import annotations

import functools
import time
from typing import Callable

__all__ = ["retry"]


def retry(max_attempts: int = 3,
          delay: float = 1.0,
          backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """Return a decorator that retries a function with exponential backoff."""
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
            attempt = 0
            while True:
                attempt += 1
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    if attempt >= max_attempts:
                        raise
                    sleep(delay * backoff ** (attempt - 1))

        wrapper.calls = 0
        return wrapper

    return decorator
