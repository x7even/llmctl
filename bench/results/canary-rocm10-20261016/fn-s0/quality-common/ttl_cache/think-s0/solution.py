"""A fixed-capacity cache with per-entry TTL and LRU eviction (stdlib only)."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable, Hashable


class TTLCache:
    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not isinstance(default_ttl, (int, float)) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")

        self._capacity: int = capacity
        self._default_ttl: float = default_ttl
        self._clock: Callable[[], float] = clock
        # OrderedDict preserves insertion/access order: first = LRU, last = MRU.
        # Each value is (value, expires_at).
        self._store: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_expired(self, expires_at: float) -> bool:
        return self._clock() >= expires_at

    def _purge_expired(self) -> None:
        now = self._clock()
        to_remove = [k for k, (_, exp) in self._store.items() if now >= exp]
        for k in to_remove:
            del self._store[k]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, key: Hashable, value: Any, ttl: float | None = None) -> None:
        if ttl is not None and (not isinstance(ttl, (int, float)) or ttl <= 0):
            raise ValueError("ttl must be > 0")

        effective_ttl = self._default_ttl if ttl is None else ttl
        now = self._clock()
        expires_at = now + effective_ttl

        if key in self._store:
            _, existing_expires = self._store[key]
            if not self._is_expired(existing_expires):
                # Overwrite a live entry: replace value, reset TTL, mark MRU.
                self._store[key] = (value, expires_at)
                self._store.move_to_end(key)
                return
            # Entry exists but is expired – remove and treat as new insert below.
            del self._store[key]

        # Inserting a *new* key – enforce capacity.
        if len(self._store) >= self._capacity:
            self._purge_expired()
            if len(self._store) >= self._capacity:
                # Evict the single least-recently-used live entry.
                self._store.popitem(last=False)

        self._store[key] = (value, expires_at)

    def get(self, key: Hashable, default: Any = None) -> Any:
        if key not in self._store:
            return default
        value, expires_at = self._store[key]
        if self._is_expired(expires_at):
            del self._store[key]
            return default
        self._store.move_to_end(key)
        return value

    def peek(self, key: Hashable, default: Any = None) -> Any:
        if key not in self._store:
            return default
        value, expires_at = self._store[key]
        if self._is_expired(expires_at):
            del self._store[key]
            return default
        return value

    def delete(self, key: Hashable) -> bool:
        if key not in self._store:
            return False
        _, expires_at = self._store[key]
        expired = self._is_expired(expires_at)
        del self._store[key]
        return not expired

    def keys(self) -> list:
        now = self._clock()
        return [k for k, (_, exp) in self._store.items() if now < exp]

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._store)

    def __contains__(self, key: Hashable) -> bool:
        if key not in self._store:
            return False
        _, expires_at = self._store[key]
        return not self._is_expired(expires_at)
