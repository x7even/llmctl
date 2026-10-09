Write a Python module implementing a `retry` decorator factory for calling flaky functions. Standard library only.

```python
def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Callable: ...
```

It is used as `@retry(max_attempts=5, delay=0.5)` (always with parentheses, even for the defaults: `@retry()`).

Behaviour:

1. The decorated function is called with the caller's arguments and its return value is returned as soon as one attempt succeeds.
2. If an attempt raises one of the `exceptions`, wait and try again, up to `max_attempts` calls in total. The wait before retry number `k` (k = 1 for the wait after the first failure) is `delay * backoff ** (k - 1)` seconds, performed by calling `sleep(seconds)`. There is no wait after the final failed attempt.
3. If every attempt fails, re-raise the exception from the **last** attempt.
4. An exception that is not an instance of one of `exceptions` propagates immediately, with no retry and no sleep.
5. `max_attempts < 1`, `delay < 0` or `backoff < 1` raise `ValueError` when `retry(...)` is called (not when the function is decorated or called).
6. The wrapper keeps the original function's `__name__`, `__doc__` and other metadata (use `functools.wraps`).
7. The wrapper has an attribute `calls` holding the total number of times the wrapped function has been invoked (across all calls to the wrapper), starting at 0.

Output requirements: reply with **one** Python code block containing the complete module. No explanation outside the code block.
