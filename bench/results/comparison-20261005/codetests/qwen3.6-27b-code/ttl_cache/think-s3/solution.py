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
        self._cache = OrderedDict()

    def _purge_expired(self) -> None:
        now = self._clock()
        to_remove = [k for k, (_, exp) in self._cache.items() if now >= exp]
        for k in to_remove:
            del self._cache[k]

    def put(self, key, value, ttl: float | None = None) -> None:
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be > 0")
        now = self._clock()
        actual_ttl = ttl if ttl is not None else self._default_ttl
        exp = now + actual_ttl
        
        is_existing_live = key in self._cache and self._cache[key][1] > now
        
        if is_existing_live:
            self._cache[key] = (value, exp)
            self._cache.move_to_end(key)
        else:
            self._purge_expired()
            if len(self._cache) >= self._capacity:
                self._cache.popitem(last=False)
            self._cache[key] = (value, exp)
            self._cache.move_to_end(key)

    def get(self, key, default=None):
        now = self._clock()
        if key in self._cache:
            value, exp = self._cache[key]
            if now >= exp:
                del self._cache[key]
                return default
            self._cache.move_to_end(key)
            return value
        return default

    def peek(self, key, default=None):
        now = self._clock()
        if key in self._cache:
            value, exp = self._cache[key]
            if now >= exp:
                del self._cache[key]
                return default
            return value
        return default

    def delete(self, key) -> bool:
        now = self._clock()
        if key in self._cache:
            _, exp = self._cache[key]
            is_live = now < exp
            del self._cache[key]
            return is_live
        return False

    def keys(self) -> list:
        self._purge_expired()
        return list(self._cache.keys())

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._cache)

    def __contains__(self, key) -> bool:
        now = self._clock()
        if key in self._cache:
            _, exp = self._cache[key]
            return now < exp
        return False
