Write a Python module implementing a `TTLCache` class: a fixed-capacity cache with per-entry time-to-live and least-recently-used eviction. Standard library only. It must be deterministic under an injected clock (the tests drive a fake clock).

```python
class TTLCache:
    def __init__(self, capacity: int, default_ttl: float, clock: Callable[[], float] = time.monotonic) -> None: ...
    def put(self, key, value, ttl: float | None = None) -> None: ...
    def get(self, key, default=None): ...
    def peek(self, key, default=None): ...
    def delete(self, key) -> bool: ...
    def keys(self) -> list: ...
    def __len__(self) -> int: ...
    def __contains__(self, key) -> bool: ...
```

Rules:

1. **Validation.** `capacity` must be an int >= 1 and `default_ttl` must be > 0, otherwise raise `ValueError`. A per-entry `ttl` passed to `put` (when not `None`) must also be > 0, otherwise `ValueError` (and the cache must be left unchanged). `float('inf')` is a valid TTL (never expires).
2. **Expiry.** An entry written at time `t` with TTL `x` expires at `t + x`; it is expired when `clock() >= t + x` (the boundary instant is already expired). `ttl=None` means "use `default_ttl`".
3. **`put(key, value, ttl=None)`.** Inserts or overwrites. Overwriting an existing, still-live key replaces its value, **resets its TTL** from the current time (using the new `ttl`, or the default if `None`), and marks it most-recently-used. Overwriting a key whose entry has already expired is treated as inserting a new key.
4. **Eviction.** When inserting a *new* key and the cache already holds `capacity` entries: first discard all expired entries; if the cache is still full, evict the single least-recently-used live entry. Overwriting an existing live key never evicts anything.
5. **`get(key, default=None)`.** Returns the value if the key is present and live, and marks it most-recently-used; it does **not** extend the TTL. If the entry is expired it is removed and `default` is returned. A missing key returns `default`.
6. **`peek(key, default=None)`.** Like `get` but does **not** change recency. Expired entries are still removed and `default` returned.
7. **`delete(key) -> bool`.** Returns `True` if a live entry was removed. Returns `False` if the key is missing or its entry had already expired (an expired entry is removed either way).
8. **`__len__`** counts live entries only (expired entries are purged first). **`__contains__`** is True only for live entries and does not change recency.
9. **`keys()`** returns the live keys ordered from least-recently-used to most-recently-used.
10. Keys may be any hashable value; values may be anything, including `None` (so a stored `None` is a hit, distinct from a miss — `get` on a key whose value is `None` returns `None` and still marks it recently used).

Output requirements: reply with **one** Python code block containing the complete module. No explanation outside the code block.
