import time
from functools import wraps
from typing import Callable, Any


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> Callable:
    """Decorator factory for retrying flaky function calls."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if delay < 0:
        raise ValueError("delay must be >= 0")
    if backoff < 1:
        raise ValueError("backoff must be >= 1")

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                wrapper.calls += 1
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt < max_attempts:
                        wait = delay * (backoff ** (attempt - 1))
                        sleep(wait)
            # All attempts failed; re-raise the last exception
            raise last_exception

        wrapper.calls = 0
        return wrapper

    return decorator
