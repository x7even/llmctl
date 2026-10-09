"""A retry decorator factory for flaky functions."""

import functools
import time
from typing import Any, Callable

__all__ = ["retry"]

_DEFAULT_SLEEP = time.sleep


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable:
    """Return a decorator that retries a function on selected exceptions."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if delay < 0:
        raise ValueError("delay must be non-negative")
    if backoff < 1:
        raise ValueError("backoff must be at least 1")

    if isinstance(exceptions, type):
        exceptions = (exceptions,)
    elif not isinstance(exceptions, tuple):
        exceptions = tuple(exceptions)

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc = None

            for attempt in range(1, max_attempts + 1):
                wrapper.calls += 1

                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc

                    if attempt == max_attempts:
                        raise

                    sleep_func = time.sleep if sleep is _DEFAULT_SLEEP else sleep
                    sleep_func(delay * (backoff ** (attempt - 1)))

            raise RuntimeError("unreachable")

        wrapper.calls = 0
        return wrapper

    return decorator
