"""A retry decorator factory for calling flaky functions.

Standard library only.
"""

import functools
import time
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> Callable:
    """Return a decorator that retries a flaky function up to *max_attempts* times.

    Parameters are validated immediately; invalid values raise ``ValueError``.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if delay < 0:
        raise ValueError("delay must be >= 0")
    if backoff < 1:
        raise ValueError("backoff must be >= 1")

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                wrapper.calls += 1
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt < max_attempts - 1:
                        k = attempt + 1  # 1-based retry index
                        sleep(delay * backoff ** (k - 1))
            raise last_exception

        wrapper.calls = 0
        return wrapper  # type: ignore[return-value]

    return decorator
