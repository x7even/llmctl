from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable, Hashable, Optional


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
        self._default_ttl = float(default_ttl)
        self._clock = clock
        # Maps key -> (value, expiry_time)
        self._data: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()

    def _purge_expired(self) -> None:
        """Remove all expired entries from the cache."""
        now = self._clock()
        expired_keys = [
            k for k, (_, expiry) in self._data.items() if now >= expiry
        ]
        for k in expired_keys:
            del self._data[k]

    def _is_expired(self, expiry: float) -> bool:
        return self._clock() >= expiry

    def put(self, key: Hashable, value: Any, ttl: Optional[float] = None) -> None:
        """Insert or overwrite a key-value pair with an optional TTL."""
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or ttl <= 0:
                raise ValueError("ttl must be > 0")
            effective_ttl = float(ttl)
        else:
            effective_ttl = self._default_ttl

        now = self._clock()
        expiry = now + effective_ttl

        # Check if key exists and is still live
        if key in self._data:
            _, existing_expiry = self._data[key]
            if not self._is_expired(existing_expiry):
                # Overwrite existing live entry: replace value, reset TTL, mark MRU
                self._data[key] = (value, expiry)
                self._data.move_to_end(key)
                return
            else:
                # Entry is expired; remove it and treat as new insert
                del self._data[key]

        # Inserting a new key: may need to evict
        self._purge_expired()
        if len(self._data) >= self._capacity:
            # Evict the LRU entry (first in the OrderedDict)
            self._data.popitem(last=False)
        self._data[key] = (value, expiry)

    def get(self, key: Hashable, default: Any = None) -> Any:
        """Retrieve a value, marking it most-recently-used. Does not extend TTL."""
        if key not in self._data:
            return default
        value, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return default
        # Mark as most-recently-used
        self._data.move_to_end(key)
        return value

    def peek(self, key: Hashable, default: Any = None) -> Any:
        """Retrieve a value without changing recency."""
        if key not in self._data:
            return default
        value, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return default
        return value

    def delete(self, key: Hashable) -> bool:
        """Delete a key. Returns True if a live entry was removed."""
        if key not in self._data:
            return False
        _, expiry = self._data[key]
        was_live = not self._is_expired(expiry)
        del self._data[key]
        return was_live

    def keys(self) -> list:
        """Return live keys ordered from LRU to MRU."""
        self._purge_expired()
        return list(self._data.keys())

    def __len__(self) -> int:
        """Count live entries only."""
        self._purge_expired()
        return len(self._data)

    def __contains__(self, key: Hashable) -> bool:
        """Check if key is present and live. Does not change recency."""
        if key not in self._data:
            return False
        _, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return False
        return True
