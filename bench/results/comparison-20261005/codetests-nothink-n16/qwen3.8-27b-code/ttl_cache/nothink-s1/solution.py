"""A fixed-capacity TTL cache with LRU eviction, driven by an injectable clock."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable


class TTLCache:
    """A fixed-capacity cache with per-entry time-to-live and LRU eviction.

    Deterministic under an injected clock.
    """

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

        self._capacity: int = capacity
        self._default_ttl: float = float(default_ttl)
        self._clock: Callable[[], float] = clock
        # key -> (value, expiry_time)
        # OrderedDict preserves insertion order; we move-to-end on access for LRU.
        self._store: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    def _now(self) -> float:
        return self._clock()

    def _is_expired(self, expiry: float, now: float | None = None) -> bool:
        if now is None:
            now = self._now()
        return now >= expiry

    def _purge_expired(self, now: float | None = None) -> None:
        if now is None:
            now = self._now()
        expired_keys = [
            k for k, (_, expiry) in self._store.items() if now >= expiry
        ]
        for k in expired_keys:
            del self._store[k]

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool):
                raise ValueError("ttl must be a number > 0 or None")
            if ttl <= 0:
                raise ValueError("ttl must be > 0")
            effective_ttl = float(ttl)
        else:
            effective_ttl = self._default_ttl

        now = self._now()
        expiry = now + effective_ttl

        # Check if key already exists and is live
        if key in self._store:
            _, existing_expiry = self._store[key]
            if now < existing_expiry:
                # Live key: overwrite value, reset TTL, mark MRU
                self._store[key] = (value, expiry)
                self._store.move_to_end(key)
                return
            else:
                # Expired: remove it, treat as new insert
                del self._store[key]

        # New key insertion
        # Purge expired entries first
        self._purge_expired(now)

        if len(self._store) >= self._capacity:
            # Evict LRU (first item in OrderedDict)
            self._store.popitem(last=False)

        self._store[key] = (value, expiry)

    def get(self, key: Any, default: Any = None) -> Any:
        now = self._now()
        if key in self._store:
            value, expiry = self._store[key]
            if now >= expiry:
                del self._store[key]
                return default
            # Live: mark MRU, do NOT extend TTL
            self._store.move_to_end(key)
            return value
        return default

    def peek(self, key: Any, default: Any = None) -> Any:
        now = self._now()
        if key in self._store:
            value, expiry = self._store[key]
            if now >= expiry:
                del self._store[key]
                return default
            # Live: do NOT change recency
            return value
        return default

    def delete(self, key: Any) -> bool:
        now = self._now()
        if key in self._store:
            _, expiry = self._store[key]
            if now >= expiry:
                del self._store[key]
                return False
            else:
                del self._store[key]
                return True
        return False

    def keys(self) -> list:
        now = self._now()
        self._purge_expired(now)
        # OrderedDict is ordered from LRU (first) to MRU (last)
        return list(self._store.keys())

    def __len__(self) -> int:
        now = self._now()
        self._purge_expired(now)
        return len(self._store)

    def __contains__(self, key: Any) -> bool:
        now = self._now()
        if key in self._store:
            _, expiry = self._store[key]
            if now >= expiry:
                del self._store[key]
                return False
            return True
        return False
