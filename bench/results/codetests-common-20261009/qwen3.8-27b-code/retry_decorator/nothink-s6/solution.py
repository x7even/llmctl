"""A retry decorator factory for calling flaky functions."""

import functools
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[F], F]:
    """
    Create a retry decorator for the given parameters.

    Args:
        max_attempts: Maximum number of times to call the function (must be >= 1).
        delay: Initial delay in seconds between retries (must be >= 0).
        backoff: Multiplier applied to delay for each subsequent retry (must be >= 1).
        exceptions: Tuple of exception types to catch and retry on.
        sleep: Callable that sleeps for the given number of seconds.

    Returns:
        A decorator that wraps a function with retry logic.

    Raises:
        ValueError: If max_attempts < 1, delay < 0, or backoff < 1.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if delay < 0:
        raise ValueError("delay must be >= 0")
    if backoff < 1:
        raise ValueError("backoff must be >= 1")

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    wrapper.calls += 1
                    return result
                except exceptions as exc:
                    wrapper.calls += 1
                    if attempt == max_attempts:
                        raise
                    wait_time = delay * (backoff ** (attempt - 1))
                    sleep(wait_time)
            # This line should never be reached, but included for safety
            raise RuntimeError("Unreachable")

        wrapper.calls = 0
        return wrapper

    return decorator
