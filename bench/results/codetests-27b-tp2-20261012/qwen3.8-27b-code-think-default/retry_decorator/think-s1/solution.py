"""A retry decorator factory for calling flaky functions."""

import time
from functools import wraps
from typing import Callable


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> Callable:
    """Decorator factory that retries a flaky function up to max_attempts times."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if delay < 0:
        raise ValueError("delay must be >= 0")
    if backoff < 1:
        raise ValueError("backoff must be >= 1")

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    wrapper.calls += 1
                    return result
                except exceptions as exc:
                    wrapper.calls += 1
                    last_exception = exc
                    if attempt < max_attempts:
                        k = attempt
                        sleep(delay * backoff ** (k - 1))
            raise last_exception

        wrapper.calls = 0
        return wrapper

    return decorator
