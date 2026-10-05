from __future__ import annotations
import time
from collections import OrderedDict
from typing import Callable, Any, Optional


class TTLCache:
    """
    A fixed-capacity cache with per-entry time-to-live and least-recently-used eviction.
    """

    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an integer >= 1")
        if not isinstance(default_ttl, (int, float)) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        # Allow inf
        if default_ttl != float("inf") and default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")

        self.capacity = capacity
        self.default_ttl = float(default_ttl)
        self.clock = clock

        # Internal storage: key -> (value, expire_time)
        # We use OrderedDict to maintain insertion/access order for LRU
        # The order is: least-recently-used at the beginning, most-recently-used at the end
        self._cache: OrderedDict = OrderedDict()

    def _is_expired(self, expire_time: float) -> bool:
        """Check if an entry is expired based on current clock."""
        if expire_time == float("inf"):
            return False
        return self.clock() >= expire_time

    def _purge_expired(self) -> None:
        """Remove all expired entries from the cache."""
        expired_keys = []
        for key, (value, expire_time) in self._cache.items():
            if self._is_expired(expire_time):
                expired_keys.append(key)
        for key in expired_keys:
            del self._cache[key]

    def _get_expire_time(self, ttl: Optional[float]) -> float:
        """Calculate expiration time given a TTL."""
        if ttl is None:
            ttl = self.default_ttl
        if ttl == float("inf"):
            return float("inf")
        return self.clock() + ttl

    def put(self, key, value, ttl: Optional[float] = None) -> None:
        """
        Inserts or overwrites an entry.
        If key exists and is live: replace value, reset TTL, mark as most-recently-used.
        If key exists but expired: treat as new insertion.
        If key doesn't exist: insert as new.
        """
        # Validate ttl if provided
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or ttl <= 0:
                raise ValueError("ttl must be > 0")
            if ttl != float("inf") and ttl <= 0:
                raise ValueError("ttl must be > 0")

        current_time = self.clock()
        expire_time = self._get_expire_time(ttl)

        # Check if key exists
        if key in self._cache:
            # Key exists, check if it's expired
            _, existing_expire_time = self._cache[key]
            if self._is_expired(existing_expire_time):
                # Treat as new insertion: remove expired entry first
                del self._cache[key]
                # Fall through to new insertion logic
            else:
                # Overwrite existing live entry
                self._cache[key] = (value, expire_time)
                # Mark as most-recently-used by moving to end
                self._cache.move_to_end(key)
                return

        # New insertion: need to handle capacity
        # First purge all expired entries
        self._purge_expired()

        # If still at capacity, evict LRU (first item in OrderedDict)
        if len(self._cache) >= self.capacity:
            # Evict the least-recently-used entry (first item)
            self._cache.popitem(last=False)

        # Insert new entry at the end (most-recently-used)
        self._cache[key] = (value, expire_time)

    def get(self, key, default=None):
        """
        Returns the value if the key is present and live, marking it most-recently-used.
        Does not extend TTL.
        If expired, removes entry and returns default.
        If missing, returns default.
        """
        if key not in self._cache:
            return default

        value, expire_time = self._cache[key]

        if self._is_expired(expire_time):
            # Remove expired entry
            del self._cache[key]
            return default

        # Mark as most-recently-used
        self._cache.move_to_end(key)
        return value

    def peek(self, key, default=None):
        """
        Like get but does not change recency.
        Expired entries are removed and default is returned.
        """
        if key not in self._cache:
            return default

        value, expire_time = self._cache[key]

        if self._is_expired(expire_time):
            # Remove expired entry
            del self._cache[key]
            return default

        # Do not change recency
        return value

    def delete(self, key) -> bool:
        """
        Returns True if a live entry was removed.
        Returns False if the key is missing or its entry had already expired.
        Expired entries are removed either way.
        """
        if key not in self._cache:
            return False

        value, expire_time = self._cache[key]

        if self._is_expired(expire_time):
            # Remove expired entry
            del self._cache[key]
            return False

        # Remove live entry
        del self._cache[key]
        return True

    def keys(self) -> list:
        """
        Returns the live keys ordered from least-recently-used to most-recently-used.
        Expired entries are purged first.
        """
        self._purge_expired()
        return list(self._cache.keys())

    def __len__(self) -> int:
        """Counts live entries only (expired entries are purged first)."""
        self._purge_expired()
        return len(self._cache)

    def __contains__(self, key) -> bool:
        """
        True only for live entries and does not change recency.
        """
        if key not in self._cache:
            return False

        value, expire_time = self._cache[key]

        if self._is_expired(expire_time):
            # Remove expired entry
            del self._cache[key]
            return False

        return True
