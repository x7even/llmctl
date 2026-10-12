"""A retry decorator factory for calling flaky functions."""

import functools
import time
from collections.abc import Callable


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> Callable:
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")
    if delay < 0:
        raise ValueError(f"delay must be >= 0, got {delay}")
    if backoff < 1:
        raise ValueError(f"backoff must be >= 1, got {backoff}")

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception: BaseException | None = None
            for attempt in range(max_attempts):
                try:
                    result = func(*args, **kwargs)
                    wrapper.calls += 1
                    return result
                except exceptions as exc:
                    last_exception = exc
                    wrapper.calls += 1
                    if attempt < max_attempts - 1:
                        k = attempt + 1
                        sleep(delay * backoff ** (k - 1))
            raise last_exception

        wrapper.calls = 0
        return wrapper

    return decorator
