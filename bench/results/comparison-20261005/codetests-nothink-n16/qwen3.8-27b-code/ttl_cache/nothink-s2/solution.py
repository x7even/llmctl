from collections import OrderedDict
from typing import Any, Callable
import time


class TTLCache:
    """A fixed-capacity LRU cache with per-entry time-to-live."""

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
        # OrderedDict: key -> (value, expires_at)
        # Order: least-recently-used first, most-recently-used last
        self._store: "OrderedDict[Any, tuple[Any, float]]" = OrderedDict()

    def _now(self) -> float:
        return self._clock()

    def _is_expired(self, expires_at: float, now: float) -> bool:
        return now >= expires_at

    def _purge_expired(self, now: float) -> None:
        """Remove all expired entries from the cache."""
        expired_keys = []
        for key in self._store:
            _, expires_at = self._store[key]
            if self._is_expired(expires_at, now):
                expired_keys.append(key)
        for key in expired_keys:
            del self._store[key]

    def _touch(self, key: Any) -> None:
        """Move key to the most-recently-used position."""
        if key in self._store:
            self._store.move_to_end(key)

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        now = self._now()

        # Validate ttl
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool):
                raise ValueError("ttl must be a number")
            if ttl <= 0:
                raise ValueError("ttl must be > 0")
            effective_ttl = float(ttl)
        else:
            effective_ttl = self._default_ttl

        expires_at = now + effective_ttl

        # Check if key already exists and is live
        if key in self._store:
            _, existing_expires_at = self._store[key]
            if self._is_expired(existing_expires_at, now):
                # Expired entry: treat as new key insertion
                del self._store[key]
            else:
                # Live entry: overwrite, reset TTL, mark MRU
                self._store[key] = (value, expires_at)
                self._store.move_to_end(key)
                return

        # New key insertion: may need to evict
        # First purge all expired entries
        self._purge_expired(now)

        # If still at capacity, evict LRU
        if len(self._store) >= self._capacity:
            # Evict the least-recently-used entry (first in OrderedDict)
            self._store.popitem(last=False)

        self._store[key] = (value, expires_at)

    def get(self, key: Any, default: Any = None) -> Any:
        now = self._now()

        if key not in self._store:
            return default

        value, expires_at = self._store[key]
        if self._is_expired(expires_at, now):
            del self._store[key]
            return default

        # Mark as most-recently-used
        self._store.move_to_end(key)
        return value

    def peek(self, key: Any, default: Any = None) -> Any:
        now = self._now()

        if key not in self._store:
            return default

        value, expires_at = self._store[key]
        if self._is_expired(expires_at, now):
            del self._store[key]
            return default

        # Do NOT change recency
        return value

    def delete(self, key: Any) -> bool:
        now = self._now()

        if key not in self._store:
            return False

        _, expires_at = self._store[key]
        if self._is_expired(expires_at, now):
            del self._store[key]
            return False

        del self._store[key]
        return True

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

        if key not in self._store:
            return False

        _, expires_at = self._store[key]
        if self._is_expired(expires_at, now):
            del self._store[key]
            return False

        return True
