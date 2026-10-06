from collections import OrderedDict
import time
from typing import Callable, Any, Hashable


class TTLCache:
    """A fixed-capacity cache with per-entry TTL and LRU eviction."""

    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not isinstance(default_ttl, (int, float)) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")

        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        # Maps key -> (value, expiry_time)
        self._store: "OrderedDict[Hashable, tuple[Any, float]]" = OrderedDict()

    def _now(self) -> float:
        return self._clock()

    def _is_expired(self, expiry: float, now: float) -> bool:
        return now >= expiry

    def _purge_expired(self, now: float) -> None:
        """Remove all expired entries."""
        expired_keys = [
            key for key, (_, expiry) in self._store.items() if self._is_expired(expiry, now)
        ]
        for key in expired_keys:
            del self._store[key]

    def put(self, key: Hashable, value: Any, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or ttl <= 0:
                raise ValueError("ttl must be > 0")
        effective_ttl = ttl if ttl is not None else self._default_ttl
        now = self._now()
        expiry = now + effective_ttl

        if key in self._store:
            # Check if the existing entry is still live
            _, existing_expiry = self._store[key]
            if self._is_expired(existing_expiry, now):
                # Expired: treat as inserting a new key
                del self._store[key]
                self._insert_new(key, value, expiry, now)
            else:
                # Live: overwrite, reset TTL, mark most-recently-used
                self._store[key] = (value, expiry)
                self._store.move_to_end(key)
        else:
            self._insert_new(key, value, expiry, now)

    def _insert_new(self, key: Hashable, value: Any, expiry: float, now: float) -> None:
        # Purge expired entries first
        self._purge_expired(now)
        # If still at capacity, evict LRU
        if len(self._store) >= self._capacity:
            # Evict the least-recently-used entry (first in OrderedDict)
            self._store.popitem(last=False)
        self._store[key] = (value, expiry)

    def get(self, key: Hashable, default: Any = None) -> Any:
        now = self._now()
        if key in self._store:
            value, expiry = self._store[key]
            if self._is_expired(expiry, now):
                del self._store[key]
                return default
            # Mark as most-recently-used
            self._store.move_to_end(key)
            return value
        return default

    def peek(self, key: Hashable, default: Any = None) -> Any:
        now = self._now()
        if key in self._store:
            value, expiry = self._store[key]
            if self._is_expired(expiry, now):
                del self._store[key]
                return default
            return value
        return default

    def delete(self, key: Hashable) -> bool:
        now = self._now()
        if key in self._store:
            _, expiry = self._store[key]
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

    def __contains__(self, key: Hashable) -> bool:
        now = self._now()
        if key in self._store:
            _, expiry = self._store[key]
            if self._is_expired(expiry, now):
                del self._store[key]
                return False
            return True
        return False
