"""A fixed-capacity cache with per-entry TTL and LRU eviction."""

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
        if not isinstance(default_ttl, (int, float)) or isinstance(default_ttl, bool):
            raise ValueError("default_ttl must be a number > 0")
        if default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")

        self._capacity = capacity
        self._default_ttl = float(default_ttl)
        self._clock = clock
        # Maps key -> (value, expire_time)
        self._store: "OrderedDict[Any, tuple[Any, float]]" = OrderedDict()

    def _now(self) -> float:
        return self._clock()

    def _is_expired(self, expire_time: float) -> bool:
        return self._now() >= expire_time

    def _purge_expired(self) -> None:
        """Remove all expired entries from the cache."""
        now = self._now()
        expired_keys = [
            key for key, (_, expire_time) in self._store.items() if now >= expire_time
        ]
        for key in expired_keys:
            del self._store[key]

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        """Insert or overwrite a key-value pair."""
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool):
                raise ValueError("ttl must be a number > 0 or None")
            if ttl <= 0:
                raise ValueError("ttl must be > 0")
            effective_ttl = float(ttl)
        else:
            effective_ttl = self._default_ttl

        now = self._now()
        expire_time = now + effective_ttl

        # Check if key already exists and is live
        if key in self._store:
            _, existing_expire = self._store[key]
            if now < existing_expire:
                # Still live: overwrite, reset TTL, mark as most recently used
                self._store[key] = (value, expire_time)
                self._store.move_to_end(key)
                return
            else:
                # Expired: treat as new key insertion
                del self._store[key]

        # New key insertion: may need eviction
        if len(self._store) >= self._capacity:
            # First, discard all expired entries
            self._purge_expired()
            if len(self._store) >= self._capacity:
                # Evict the least recently used live entry
                self._store.popitem(last=False)

        self._store[key] = (value, expire_time)

    def get(self, key: Any, default: Any = None) -> Any:
        """Get a value by key, marking it as most recently used. Returns default if missing or expired."""
        if key in self._store:
            value, expire_time = self._store[key]
            now = self._now()
            if now >= expire_time:
                # Expired: remove and return default
                del self._store[key]
                return default
            # Live: mark as most recently used
            self._store.move_to_end(key)
            return value
        return default

    def peek(self, key: Any, default: Any = None) -> Any:
        """Get a value by key without changing recency. Returns default if missing or expired."""
        if key in self._store:
            value, expire_time = self._store[key]
            now = self._now()
            if now >= expire_time:
                # Expired: remove and return default
                del self._store[key]
                return default
            # Live: do NOT change recency
            return value
        return default

    def delete(self, key: Any) -> bool:
        """Delete a key. Returns True if a live entry was removed, False otherwise."""
        if key in self._store:
            _, expire_time = self._store[key]
            now = self._now()
            if now >= expire_time:
                # Expired: remove and return False
                del self._store[key]
                return False
            # Live: remove and return True
            del self._store[key]
            return True
        return False

    def keys(self) -> list:
        """Return live keys ordered from least-recently-used to most-recently-used."""
        self._purge_expired()
        return list(self._store.keys())

    def __len__(self) -> int:
        """Return the number of live entries."""
        self._purge_expired()
        return len(self._store)

    def __contains__(self, key: Any) -> bool:
        """Return True if the key is present and live. Does not change recency."""
        if key in self._store:
            _, expire_time = self._store[key]
            now = self._now()
            if now >= expire_time:
                # Expired: remove
                del self._store[key]
                return False
            return True
        return False
