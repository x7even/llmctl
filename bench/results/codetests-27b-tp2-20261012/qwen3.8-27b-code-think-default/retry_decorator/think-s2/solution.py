"""A retry decorator factory for calling flaky functions."""

import functools
import time
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> Callable:
    """Return a decorator that retries a flaky function up to *max_attempts* times."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if delay < 0:
        raise ValueError("delay must be >= 0")
    if backoff < 1:
        raise ValueError("backoff must be >= 1")

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
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
                        sleep(delay * backoff ** attempt)
            raise last_exception

        wrapper.calls = 0  # type: ignore[attr-defined]
        return wrapper

    return decorator
