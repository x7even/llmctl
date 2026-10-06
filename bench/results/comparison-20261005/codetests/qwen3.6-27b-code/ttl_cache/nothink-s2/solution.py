import time
from collections import OrderedDict
from typing import Callable


class TTLCache:
    def __init__(self, capacity: int, default_ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not isinstance(default_ttl, (int, float)) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        
        self._capacity = capacity
        self._default_ttl = float(default_ttl)
        self._clock = clock
        # OrderedDict: key -> [value, expiry_time]
        # Order: least-recently-used at front, most-recently-used at back
        self._cache = OrderedDict()

    def _purge_expired(self) -> None:
        """Remove all expired entries from the cache."""
        now = self._clock()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if now >= expiry
        ]
        for key in expired_keys:
            del self._cache[key]

    def _is_expired(self, key) -> bool:
        """Check if a key is expired. Assumes key exists in cache."""
        now = self._clock()
        return now >= self._cache[key][1]

    def put(self, key, value, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or ttl <= 0:
                raise ValueError("ttl must be > 0")
            entry_ttl = float(ttl)
        else:
            entry_ttl = self._default_ttl

        now = self._clock()
        expiry = now + entry_ttl

        # If key already exists, update it (no eviction needed)
        if key in self._cache:
            self._cache[key] = [value, expiry]
            self._cache.move_to_end(key)
            return

        # Key does not exist: need to insert
        # First, purge all expired entries
        self._purge_expired()

        # If still at capacity, evict LRU
        if len(self._cache) >= self._capacity:
            # Pop the first item (LRU)
            self._cache.popitem(last=False)

        self._cache[key] = [value, expiry]
        # It's already at the end as most recently used

    def get(self, key, default=None):
        if key not in self._cache:
            return default

        if self._is_expired(key):
            del self._cache[key]
            return default

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return self._cache[key][0]

    def peek(self, key, default=None):
        if key not in self._cache:
            return default

        if self._is_expired(key):
            del self._cache[key]
            return default

        # Do NOT change recency
        return self._cache[key][0]

    def delete(self, key) -> bool:
        if key not in self._cache:
            return False

        if self._is_expired(key):
            del self._cache[key]
            return False

        del self._cache[key]
        return True

    def keys(self) -> list:
        # Purge expired first
        self._purge_expired()
        # Return keys from LRU to MRU (front to back)
        return list(self._cache.keys())

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._cache)

    def __contains__(self, key) -> bool:
        if key not in self._cache:
            return False

        if self._is_expired(key):
            del self._cache[key]
            return False

        # Do not change recency
        return True
