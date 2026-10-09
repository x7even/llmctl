import functools
import time


def retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(Exception,), sleep=time.sleep):
    if max_attempts < 1 or delay < 0 or backoff < 1:
        raise ValueError("invalid retry parameters")

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                wrapper.calls += 1
                try:
                    return fn(*args, **kwargs)
                except exceptions:
                    if attempt == max_attempts:
                        raise
                    sleep(delay * backoff ** (attempt - 1))

        wrapper.calls = 0
        return wrapper

    return deco
