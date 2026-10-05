import time
from collections import OrderedDict
from typing import Callable

class TTLCache:
    def __init__(self, capacity: int, default_ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        self._cache: OrderedDict = OrderedDict()

    def _purge_expired(self) -> None:
        now = self._clock()
        expired_keys = [k for k, (_, exp) in self._cache.items() if now >= exp]
        for k in expired_keys:
            del self._cache[k]

    def put(self, key, value, ttl: float | None = None) -> None:
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be > 0")
        now = self._clock()
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expiry = now + effective_ttl

        if key in self._cache:
            _, old_expiry = self._cache[key]
            if now < old_expiry:
                self._cache[key] = (value, expiry)
                self._cache.move_to_end(key)
                return
            del self._cache[key]

        if len(self._cache) >= self._capacity:
            self._purge_expired()
            if len(self._cache) >= self._capacity:
                self._cache.popitem(last=False)

        self._cache[key] = (value, expiry)

    def get(self, key, default=None):
        if key not in self._cache:
            return default
        value, expiry = self._cache[key]
        now = self._clock()
        if now >= expiry:
            del self._cache[key]
            return default
        self._cache.move_to_end(key)
        return value

    def peek(self, key, default=None):
        if key not in self._cache:
            return default
        value, expiry = self._cache[key]
        now = self._clock()
        if now >= expiry:
            del self._cache[key]
            return default
        return value

    def delete(self, key) -> bool:
        if key not in self._cache:
            return False
        _, expiry = self._cache[key]
        now = self._clock()
        if now >= expiry:
            del self._cache[key]
            return False
        del self._cache[key]
        return True

    def keys(self) -> list:
        self._purge_expired()
        return list(self._cache.keys())

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._cache)

    def __contains__(self, key) -> bool:
        if key not in self._cache:
            return False
        _, expiry = self._cache[key]
        return self._clock() < expiry
