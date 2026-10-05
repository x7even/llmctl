import time
from collections import OrderedDict
from typing import Callable


class TTLCache:
    """
    A fixed-capacity cache with per-entry time-to-live and least-recently-used eviction.
    Standard library only. Deterministic under an injected clock.
    """

    def __init__(self, capacity: int, default_ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not isinstance(default_ttl, (int, float)) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        
        self.capacity = capacity
        self.default_ttl = float(default_ttl)
        self.clock = clock
        
        # _store: OrderedDict[key -> (value, expiry_time)]
        # Order: least-recently-used at the front (left), most-recently-used at the back (right)
        self._store: OrderedDict = OrderedDict()

    def _is_expired(self, expiry_time: float) -> bool:
        """Check if an entry is expired based on current clock time."""
        if expiry_time == float('inf'):
            return False
        return self.clock() >= expiry_time

    def _purge_expired(self) -> None:
        """Remove all expired entries from the cache."""
        expired_keys = []
        for key, (value, expiry_time) in self._store.items():
            if self._is_expired(expiry_time):
                expired_keys.append(key)
        for key in expired_keys:
            del self._store[key]

    def _move_to_end(self, key: str) -> None:
        """Mark a key as most-recently-used by moving it to the end of the OrderedDict."""
        self._store.move_to_end(key)

    def _evict_lru(self) -> None:
        """Evict the least-recently-used entry (the first item in the OrderedDict)."""
        if self._store:
            self._store.popitem(last=False)

    def put(self, key, value, ttl: float | None = None) -> None:
        """
        Inserts or overwrites an entry.
        If ttl is None, uses default_ttl.
        If ttl is provided, it must be > 0.
        """
        # Validate ttl if provided
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or ttl <= 0:
                raise ValueError("ttl must be > 0 if provided")
            entry_ttl = float(ttl)
        else:
            entry_ttl = self.default_ttl

        now = self.clock()
        expiry_time = now + entry_ttl if entry_ttl != float('inf') else float('inf')

        # If key already exists
        if key in self._store:
            # Check if it's expired
            _, old_expiry = self._store[key]
            if self._is_expired(old_expiry):
                # Treat as new key insertion
                del self._store[key]
                # Fall through to new key logic
            else:
                # Overwrite existing live key: replace value, reset TTL, mark as MRU
                self._store[key] = (value, expiry_time)
                self._move_to_end(key)
                return

        # New key insertion (or overwrite of expired key)
        # First, purge all expired entries
        self._purge_expired()

        # If cache is full, evict LRU
        if len(self._store) >= self.capacity:
            self._evict_lru()

        # Insert new entry
        self._store[key] = (value, expiry_time)
        # It's already at the end (most recently used)

    def get(self, key, default=None):
        """
        Returns the value if the key is present and live, and marks it most-recently-used.
        Does not extend the TTL.
        If expired, removes entry and returns default.
        If missing, returns default.
        """
        if key not in self._store:
            return default

        value, expiry_time = self._store[key]

        if self._is_expired(expiry_time):
            del self._store[key]
            return default

        # Mark as most-recently-used
        self._move_to_end(key)
        return value

    def peek(self, key, default=None):
        """
        Like get but does not change recency.
        Expired entries are removed and default returned.
        """
        if key not in self._store:
            return default

        value, expiry_time = self._store[key]

        if self._is_expired(expiry_time):
            del self._store[key]
            return default

        return value

    def delete(self, key) -> bool:
        """
        Returns True if a live entry was removed.
        Returns False if the key is missing or its entry had already expired.
        An expired entry is removed either way.
        """
        if key not in self._store:
            return False

        value, expiry_time = self._store[key]

        if self._is_expired(expiry_time):
            del self._store[key]
            return False

        del self._store[key]
        return True

    def keys(self) -> list:
        """
        Returns the live keys ordered from least-recently-used to most-recently-used.
        Expired entries are purged first.
        """
        self._purge_expired()
        return list(self._store.keys())

    def __len__(self) -> int:
        """Counts live entries only (expired entries are purged first)."""
        self._purge_expired()
        return len(self._store)

    def __contains__(self, key) -> bool:
        """
        True only for live entries and does not change recency.
        """
        if key not in self._store:
            return False

        value, expiry_time = self._store[key]

        if self._is_expired(expiry_time):
            del self._store[key]
            return False

        return True
