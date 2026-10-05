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
        if not isinstance(capacity, int) or isinstance(capacity, bool):
            raise ValueError("capacity must be an int")
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if not isinstance(default_ttl, (int, float)) or isinstance(default_ttl, bool):
            raise ValueError("default_ttl must be a number")
        if default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")

        self._capacity: int = capacity
        self._default_ttl: float = float(default_ttl)
        self._clock: Callable[[], float] = clock
        # key -> (value, expires_at)
        self._store: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    def _now(self) -> float:
        return self._clock()

    def _is_expired(self, expires_at: float, now: float) -> bool:
        return now >= expires_at

    def _purge_expired(self, now: float) -> None:
        expired_keys = [
            k for k, (_, exp) in self._store.items() if self._is_expired(exp, now)
        ]
        for k in expired_keys:
            del self._store[k]

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool):
                raise ValueError("ttl must be a number")
            if ttl <= 0:
                raise ValueError("ttl must be > 0")
            ttl = float(ttl)
        else:
            ttl = self._default_ttl

        now = self._now()
        expires_at = now + ttl

        # Check if key already exists and is live
        if key in self._store:
            _, existing_exp = self._store[key]
            if self._is_expired(existing_exp, now):
                # Treat as new key: remove expired entry first
                del self._store[key]
                # Fall through to insertion logic below
                self._purge_expired(now)
                if len(self._store) >= self._capacity:
                    # Evict LRU
                    self._store.popitem(last=False)
                self._store[key] = (value, expires_at)
                return
            else:
                # Overwrite existing live key: replace value, reset TTL, mark MRU
                self._store[key] = (value, expires_at)
                self._store.move_to_end(key)
                return

        # New key insertion
        self._purge_expired(now)
        if len(self._store) >= self._capacity:
            # Evict LRU
            self._store.popitem(last=False)
        self._store[key] = (value, expires_at)

    def get(self, key: Any, default: Any = None) -> Any:
        now = self._now()
        if key in self._store:
            value, expires_at = self._store[key]
            if self._is_expired(expires_at, now):
                del self._store[key]
                return default
            # Mark as most recently used
            self._store.move_to_end(key)
            return value
        return default

    def peek(self, key: Any, default: Any = None) -> Any:
        now = self._now()
        if key in self._store:
            value, expires_at = self._store[key]
            if self._is_expired(expires_at, now):
                del self._store[key]
                return default
            return value
        return default

    def delete(self, key: Any) -> bool:
        now = self._now()
        if key in self._store:
            _, expires_at = self._store[key]
            if self._is_expired(expires_at, now):
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
            _, expires_at = self._store[key]
            if self._is_expired(expires_at, now):
                del self._store[key]
                return False
            return True
        return False
