from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable


class TTLCache:
    """A fixed-capacity cache with per-entry TTL and LRU eviction."""

    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not isinstance(default_ttl, (int, float)) or isinstance(default_ttl, bool):
            raise ValueError("default_ttl must be a number > 0")
        if default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")

        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        # key -> (value, expiry_time)
        self._data: "OrderedDict[Any, tuple[Any, float]]" = OrderedDict()

    def _now(self) -> float:
        return self._clock()

    def _is_expired(self, key: Any, now: float) -> bool:
        entry = self._data.get(key)
        if entry is None:
            return True
        _, expiry = entry
        return now >= expiry

    def _purge_expired(self, now: float) -> None:
        expired_keys = []
        for k, (_, expiry) in self._data.items():
            if now >= expiry:
                expired_keys.append(k)
        for k in expired_keys:
            del self._data[k]

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool):
                raise ValueError("ttl must be a number > 0")
            if ttl <= 0:
                raise ValueError("ttl must be > 0")
        else:
            ttl = self._default_ttl

        now = self._now()
        expiry = now + ttl

        if key in self._data:
            # Check if existing entry is expired
            if self._is_expired(key, now):
                # Treat as new key: remove expired entry first
                del self._data[key]
                self._insert_new(key, value, expiry, now)
            else:
                # Overwrite existing live key
                self._data[key] = (value, expiry)
                self._data.move_to_end(key)
        else:
            self._insert_new(key, value, expiry, now)

    def _insert_new(self, key: Any, value: Any, expiry: float, now: float) -> None:
        # Purge expired entries first
        self._purge_expired(now)

        if len(self._data) >= self._capacity:
            # Evict LRU (first item in OrderedDict)
            lru_key, _ = self._data.popitem(last=False)
            _ = lru_key  # discarded

        self._data[key] = (value, expiry)

    def get(self, key: Any, default: Any = None) -> Any:
        now = self._now()
        if key in self._data:
            if self._is_expired(key, now):
                del self._data[key]
                return default
            value, _ = self._data[key]
            self._data.move_to_end(key)
            return value
        return default

    def peek(self, key: Any, default: Any = None) -> Any:
        now = self._now()
        if key in self._data:
            if self._is_expired(key, now):
                del self._data[key]
                return default
            value, _ = self._data[key]
            return value
        return default

    def delete(self, key: Any) -> bool:
        now = self._now()
        if key in self._data:
            if self._is_expired(key, now):
                del self._data[key]
                return False
            del self._data[key]
            return True
        return False

    def keys(self) -> list:
        now = self._now()
        self._purge_expired(now)
        return list(self._data.keys())

    def __len__(self) -> int:
        now = self._now()
        self._purge_expired(now)
        return len(self._data)

    def __contains__(self, key: Any) -> bool:
        now = self._now()
        if key in self._data:
            if self._is_expired(key, now):
                del self._data[key]
                return False
            return True
        return False
