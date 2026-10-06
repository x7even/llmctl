from collections import OrderedDict
from typing import Any, Callable
import time


class TTLCache:
    """A fixed-capacity cache with per-entry TTL and LRU eviction."""

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
        # OrderedDict: key -> (value, expires_at)
        self._store: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    def _now(self) -> float:
        return self._clock()

    def _is_expired(self, expires_at: float, now: float) -> bool:
        return now >= expires_at

    def _purge_expired(self, now: float) -> None:
        """Remove all expired entries from the store."""
        to_remove = []
        for key, (_, expires_at) in self._store.items():
            if self._is_expired(expires_at, now):
                to_remove.append(key)
        for key in to_remove:
            del self._store[key]

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        now = self._now()

        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or ttl <= 0:
                raise ValueError("ttl must be > 0")
            effective_ttl = ttl
        else:
            effective_ttl = self._default_ttl

        expires_at = now + effective_ttl

        # Check if key already exists and is live
        if key in self._store:
            _, existing_expires = self._store[key]
            if not self._is_expired(existing_expires, now):
                # Overwrite existing live entry: reset TTL, mark MRU
                self._store[key] = (value, expires_at)
                self._store.move_to_end(key)
                return
            else:
                # Expired entry: treat as new insert, remove it first
                del self._store[key]

        # Inserting a new key
        # First, purge all expired entries
        self._purge_expired(now)

        # If still at capacity, evict LRU
        if len(self._store) >= self._capacity:
            # Evict the least-recently-used entry (first item in OrderedDict)
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

        # Do NOT change recency
        return True
