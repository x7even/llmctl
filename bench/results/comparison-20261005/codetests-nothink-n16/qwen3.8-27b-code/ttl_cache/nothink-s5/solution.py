from collections import OrderedDict
from typing import Any, Callable
import time


class TTLCache:
    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not isinstance(default_ttl, (int, float)) or isinstance(default_ttl, bool) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        # key -> (value, expiry_time)
        self._data: "OrderedDict[Any, tuple[Any, float]]" = OrderedDict()

    def _is_expired(self, expiry: float) -> bool:
        return self._clock() >= expiry

    def _purge_expired(self) -> None:
        to_remove = [k for k, (_, expiry) in self._data.items() if self._is_expired(expiry)]
        for k in to_remove:
            del self._data[k]

    def put(self, key, value, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or ttl <= 0:
                raise ValueError("ttl must be > 0")
        effective_ttl = ttl if ttl is not None else self._default_ttl
        now = self._clock()
        expiry = now + effective_ttl

        if key in self._data:
            _, old_expiry = self._data[key]
            if self._is_expired(old_expiry):
                # Treat as new key: remove old entry first
                del self._data[key]
                self._insert_new(key, value, expiry)
            else:
                # Overwrite existing live key
                self._data[key] = (value, expiry)
                self._data.move_to_end(key)
        else:
            self._insert_new(key, value, expiry)

    def _insert_new(self, key, value, expiry: float) -> None:
        self._purge_expired()
        if len(self._data) >= self._capacity:
            # Evict LRU
            self._data.popitem(last=False)
        self._data[key] = (value, expiry)
        self._data.move_to_end(key)

    def get(self, key, default=None):
        if key not in self._data:
            return default
        value, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return default
        self._data.move_to_end(key)
        return value

    def peek(self, key, default=None):
        if key not in self._data:
            return default
        value, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return default
        return value

    def delete(self, key) -> bool:
        if key not in self._data:
            return False
        _, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return False
        del self._data[key]
        return True

    def keys(self) -> list:
        self._purge_expired()
        return list(self._data.keys())

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._data)

    def __contains__(self, key) -> bool:
        if key not in self._data:
            return False
        _, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return False
        return True
