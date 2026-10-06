from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable, Hashable


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

        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        # OrderedDict: key -> (value, expiry_time)
        # Order reflects LRU: first item is LRU, last is MRU
        self._data: "OrderedDict[Hashable, tuple[Any, float]]" = OrderedDict()

    def _now(self) -> float:
        return self._clock()

    def _is_expired(self, expiry: float, now: float) -> bool:
        return now >= expiry

    def _purge_expired(self, now: float) -> None:
        """Remove all expired entries from the cache."""
        to_remove = []
        for key, (_, expiry) in self._data.items():
            if self._is_expired(expiry, now):
                to_remove.append(key)
        for key in to_remove:
            del self._data[key]

    def _evict_lru(self) -> None:
        """Evict the least-recently-used entry."""
        if self._data:
            self._data.popitem(last=False)

    def put(self, key: Hashable, value: Any, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool):
                raise ValueError("ttl must be a number or None")
            if ttl <= 0:
                raise ValueError("ttl must be > 0")

        now = self._now()
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expiry = now + effective_ttl

        if key in self._data:
            old_value, old_expiry = self._data[key]
            if self._is_expired(old_expiry, now):
                # Expired entry: treat as new insertion
                del self._data[key]
            else:
                # Live entry: overwrite, reset TTL, mark MRU
                self._data[key] = (value, expiry)
                self._data.move_to_end(key)
                return

        # Inserting a new key
        # First purge expired entries
        self._purge_expired(now)

        if len(self._data) >= self._capacity:
            # Still full after purging: evict LRU
            self._evict_lru()

        self._data[key] = (value, expiry)
        # New entry is MRU
        self._data.move_to_end(key)

    def get(self, key: Hashable, default: Any = None) -> Any:
        now = self._now()

        if key not in self._data:
            return default

        value, expiry = self._data[key]
        if self._is_expired(expiry, now):
            del self._data[key]
            return default

        # Mark as MRU
        self._data.move_to_end(key)
        return value

    def peek(self, key: Hashable, default: Any = None) -> Any:
        now = self._now()

        if key not in self._data:
            return default

        value, expiry = self._data[key]
        if self._is_expired(expiry, now):
            del self._data[key]
            return default

        return value

    def delete(self, key: Hashable) -> bool:
        now = self._now()

        if key not in self._data:
            return False

        value, expiry = self._data[key]
        if self._is_expired(expiry, now):
            del self._data[key]
            return False

        del self._data[key]
        return True

    def keys(self) -> list:
        now = self._now()
        self._purge_expired(now)
        return list(self._data.keys())

    def __len__(self) -> int:
        now = self._now()
        self._purge_expired(now)
        return len(self._data)

    def __contains__(self, key: Hashable) -> bool:
        now = self._now()

        if key not in self._data:
            return False

        _, expiry = self._data[key]
        if self._is_expired(expiry, now):
            del self._data[key]
            return False

        return True
