from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable


class TTLCache:
    """A fixed-capacity cache with per-entry TTL and LRU eviction.

    Deterministic under an injected clock.
    """

    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool):
            raise ValueError("capacity must be an int")
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if not isinstance(default_ttl, (int, float)) or isinstance(default_ttl, bool):
            raise ValueError("default_ttl must be a number")
        if default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")

        self._capacity = capacity
        self._default_ttl = float(default_ttl)
        self._clock = clock
        # key -> (value, expiry_time)
        self._store: "OrderedDict[Any, tuple[Any, float]]" = OrderedDict()

    def _now(self) -> float:
        return self._clock()

    def _is_expired(self, expiry: float, now: float) -> bool:
        return now >= expiry

    def _purge_expired(self, now: float) -> None:
        """Remove all expired entries. Mutates self._store."""
        expired_keys = []
        for key, (_val, expiry) in self._store.items():
            if self._is_expired(expiry, now):
                expired_keys.append(key)
        for key in expired_keys:
            del self._store[key]

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool):
                raise ValueError("ttl must be a number")
            if ttl <= 0:
                raise ValueError("ttl must be > 0")
            effective_ttl = float(ttl)
        else:
            effective_ttl = self._default_ttl

        now = self._now()

        # Check if key exists and is live
        if key in self._store:
            _val, expiry = self._store[key]
            if self._is_expired(expiry, now):
                # Treat as inserting a new key: remove the expired entry
                del self._store[key]
                # Fall through to insertion logic below
            else:
                # Overwrite existing live entry: reset TTL, mark MRU
                self._store[key] = (value, now + effective_ttl)
                self._store.move_to_end(key)
                return

        # At this point, we are inserting a new key (or re-inserting after expiry)
        # Purge expired entries first
        self._purge_expired(now)

        # If cache is full, evict LRU
        if len(self._store) >= self._capacity:
            # Evict the least-recently-used (first item)
            self._store.popitem(last=False)

        self._store[key] = (value, now + effective_ttl)

    def get(self, key: Any, default: Any = None) -> Any:
        now = self._now()
        if key in self._store:
            _val, expiry = self._store[key]
            if self._is_expired(expiry, now):
                del self._store[key]
                return default
            # Live entry: mark MRU, return value
            value = _val
            self._store.move_to_end(key)
            return value
        return default

    def peek(self, key: Any, default: Any = None) -> Any:
        now = self._now()
        if key in self._store:
            _val, expiry = self._store[key]
            if self._is_expired(expiry, now):
                del self._store[key]
                return default
            return _val
        return default

    def delete(self, key: Any) -> bool:
        now = self._now()
        if key in self._store:
            _val, expiry = self._store[key]
            if self._is_expired(expiry, now):
                del self._store[key]
                return False
            else:
                del self._store[key]
                return True
        return False

    def keys(self) -> list:
        now = self._now()
        self._purge_expired(now)
        return list(self._store.keys())

    def __len__(self) -> int:
        now = self._now()
        self._purge_expired(now)
        return len(self._store)

    def __contains__(self, key: Any) -> bool:
        now = self._now()
        if key in self._store:
            _val, expiry = self._store[key]
            if self._is_expired(expiry, now):
                del self._store[key]
                return False
            return True
        return False
