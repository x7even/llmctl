"""A retry decorator factory for calling flaky functions."""

from __future__ import annotations

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
    """Decorator factory that retries a flaky function with exponential backoff."""
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")
    if delay < 0:
        raise ValueError(f"delay must be >= 0, got {delay}")
    if backoff < 1:
        raise ValueError(f"backoff must be >= 1, got {backoff}")

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exc: BaseException | None = None
            for attempt in range(max_attempts):
                try:
                    wrapper.calls += 1
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_attempts - 1:
                        k = attempt + 1
                        sleep(delay * backoff ** (k - 1))
            assert last_exc is not None
            raise last_exc

        wrapper.calls = 0  # type: ignore[attr-defined]
        return wrapper

    return decorator
