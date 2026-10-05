from collections import OrderedDict
from typing import Callable, Any
import time


class TTLCache:
    def __init__(self, capacity: int, default_ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not isinstance(default_ttl, (int, float)) or isinstance(default_ttl, bool) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        # key -> (value, expiry_time)
        # OrderedDict maintains LRU order: least recently used at front, most recently used at back
        self._store: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    def _purge_expired(self) -> None:
        now = self._clock()
        expired_keys = []
        for key, (_, expiry) in self._store.items():
            if now >= expiry:
                expired_keys.append(key)
        for key in expired_keys:
            del self._store[key]

    def _is_expired(self, key: Any) -> bool:
        if key not in self._store:
            return True
        _, expiry = self._store[key]
        return self._clock() >= expiry

    def put(self, key, value, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or ttl <= 0:
                raise ValueError("ttl must be > 0")
            effective_ttl = ttl
        else:
            effective_ttl = self._default_ttl

        now = self._clock()
        expiry = now + effective_ttl

        if key in self._store:
            # Check if existing entry is expired
            _, old_expiry = self._store[key]
            if now >= old_expiry:
                # Treat as inserting a new key
                del self._store[key]
                self._insert_new(key, value, expiry)
            else:
                # Overwrite existing live key
                self._store[key] = (value, expiry)
                self._store.move_to_end(key)
        else:
            self._insert_new(key, value, expiry)

    def _insert_new(self, key, value, expiry: float) -> None:
        # Purge expired entries first
        self._purge_expired()
        if len(self._store) >= self._capacity:
            # Evict LRU (first item in OrderedDict)
            self._store.popitem(last=False)
        self._store[key] = (value, expiry)

    def get(self, key, default=None):
        if key not in self._store:
            return default
        _, expiry = self._store[key]
        if self._clock() >= expiry:
            del self._store[key]
            return default
        value, _ = self._store[key]
        self._store.move_to_end(key)
        return value

    def peek(self, key, default=None):
        if key not in self._store:
            return default
        _, expiry = self._store[key]
        if self._clock() >= expiry:
            del self._store[key]
            return default
        value, _ = self._store[key]
        return value

    def delete(self, key) -> bool:
        if key not in self._store:
            return False
        _, expiry = self._store[key]
        if self._clock() >= expiry:
            del self._store[key]
            return False
        del self._store[key]
        return True

    def keys(self) -> list:
        self._purge_expired()
        return list(self._store.keys())

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._store)

    def __contains__(self, key) -> bool:
        if key not in self._store:
            return False
        _, expiry = self._store[key]
        if self._clock() >= expiry:
            del self._store[key]
            return False
        return True
