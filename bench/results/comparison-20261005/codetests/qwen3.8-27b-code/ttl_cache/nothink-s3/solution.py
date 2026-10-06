from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable


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
        if default_ttl is None or not isinstance(default_ttl, (int, float)) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")

        self._capacity = capacity
        self._default_ttl = float(default_ttl)
        self._clock = clock
        # key -> (value, expires_at)
        self._store: "OrderedDict[Any, tuple[Any, float]]" = OrderedDict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _purge_expired(self) -> None:
        """Remove all expired entries."""
        now = self._clock()
        expired_keys = [
            k for k, (_, exp) in self._store.items() if now >= exp
        ]
        for k in expired_keys:
            del self._store[k]

    def _is_expired(self, expires_at: float) -> bool:
        return self._clock() >= expires_at

    def _evict_if_needed(self) -> None:
        """Evict LRU entry if cache is at capacity."""
        if len(self._store) >= self._capacity:
            # First purge expired
            self._purge_expired()
            if len(self._store) >= self._capacity:
                # Evict the LRU (first item in OrderedDict)
                self._store.popitem(last=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or ttl <= 0:
                raise ValueError("ttl must be > 0")
            effective_ttl = float(ttl)
        else:
            effective_ttl = self._default_ttl

        now = self._clock()
        expires_at = now + effective_ttl

        if key in self._store:
            # Check if the existing entry is expired
            _, existing_exp = self._store[key]
            if self._clock() >= existing_exp:
                # Treat as new insertion: remove expired entry first
                del self._store[key]
                self._purge_expired()
                self._evict_if_needed()
                self._store[key] = (value, expires_at)
            else:
                # Overwrite live entry: replace value, reset TTL, mark MRU
                self._store[key] = (value, expires_at)
                self._store.move_to_end(key)
        else:
            # New key
            self._purge_expired()
            self._evict_if_needed()
            self._store[key] = (value, expires_at)

    def get(self, key: Any, default: Any = None) -> Any:
        if key not in self._store:
            return default
        value, expires_at = self._store[key]
        if self._clock() >= expires_at:
            del self._store[key]
            return default
        # Mark as most-recently-used
        self._store.move_to_end(key)
        return value

    def peek(self, key: Any, default: Any = None) -> Any:
        if key not in self._store:
            return default
        value, expires_at = self._store[key]
        if self._clock() >= expires_at:
            del self._store[key]
            return default
        # Do NOT change recency
        return value

    def delete(self, key: Any) -> bool:
        if key not in self._store:
            return False
        _, expires_at = self._store[key]
        if self._clock() >= expires_at:
            del self._store[key]
            return False
        del self._store[key]
        return True

    def keys(self) -> list:
        self._purge_expired()
        return list(self._store.keys())

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._store)

    def __contains__(self, key: Any) -> bool:
        if key not in self._store:
            return False
        _, expires_at = self._store[key]
        if self._clock() >= expires_at:
            del self._store[key]
            return False
        return True
