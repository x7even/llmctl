from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable


class TTLCache:
    """A fixed-capacity cache with per-entry time-to-live and LRU eviction."""

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
        # key -> (value, expires_at)
        self._store: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    def _is_expired(self, expires_at: float) -> bool:
        return self._clock() >= expires_at

    def _purge_expired(self) -> None:
        """Remove all expired entries from the store."""
        now = self._clock()
        expired_keys = [k for k, (_, exp) in self._store.items() if now >= exp]
        for k in expired_keys:
            del self._store[k]

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        # Validate ttl if provided
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or ttl <= 0:
                raise ValueError("ttl must be > 0")

        now = self._clock()
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = now + effective_ttl

        # Check if key exists and is live
        if key in self._store:
            _, existing_exp = self._store[key]
            if now < existing_exp:
                # Live entry: overwrite, reset TTL, mark MRU
                self._store[key] = (value, expires_at)
                self._store.move_to_end(key)
            else:
                # Expired entry: treat as new insertion
                del self._store[key]
                self._insert_new(key, value, expires_at)
        else:
            self._insert_new(key, value, expires_at)

    def _insert_new(self, key: Any, value: Any, expires_at: float) -> None:
        """Insert a new key, evicting if necessary."""
        self._purge_expired()
        if len(self._store) >= self._capacity:
            # Evict LRU (first key in OrderedDict)
            self._store.popitem(last=False)
        self._store[key] = (value, expires_at)

    def get(self, key: Any, default: Any = None) -> Any:
        if key in self._store:
            value, expires_at = self._store[key]
            if self._is_expired(expires_at):
                del self._store[key]
                return default
            # Live: mark MRU, do not extend TTL
            self._store.move_to_end(key)
            return value
        return default

    def peek(self, key: Any, default: Any = None) -> Any:
        if key in self._store:
            value, expires_at = self._store[key]
            if self._is_expired(expires_at):
                del self._store[key]
                return default
            return value
        return default

    def delete(self, key: Any) -> bool:
        if key in self._store:
            _, expires_at = self._store[key]
            if self._is_expired(expires_at):
                del self._store[key]
                return False
            del self._store[key]
            return True
        return False

    def keys(self) -> list:
        self._purge_expired()
        return list(self._store.keys())

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._store)

    def __contains__(self, key: Any) -> bool:
        if key in self._store:
            _, expires_at = self._store[key]
            if self._is_expired(expires_at):
                del self._store[key]
                return False
            return True
        return False
