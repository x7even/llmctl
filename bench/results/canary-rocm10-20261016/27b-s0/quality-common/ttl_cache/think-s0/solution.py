from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable


class TTLCache:
    """Fixed-capacity cache with per-entry TTL and LRU eviction."""

    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        # key -> (value, expires_at)
        self._store: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_expired(self, expires_at: float) -> bool:
        return self._clock() >= expires_at

    def _purge_expired(self) -> None:
        now = self._clock()
        expired = [k for k, (_, exp) in self._store.items() if now >= exp]
        for k in expired:
            del self._store[k]

    def _insert_new(self, key: Any, value: Any, expires_at: float) -> None:
        if len(self._store) >= self._capacity:
            self._purge_expired()
            if len(self._store) >= self._capacity:
                self._store.popitem(last=False)  # evict LRU
        self._store[key] = (value, expires_at)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be > 0")

        effective_ttl = ttl if ttl is not None else self._default_ttl
        now = self._clock()
        expires_at = now + effective_ttl

        if key in self._store:
            _, existing_exp = self._store[key]
            if self._is_expired(existing_exp):
                # Expired: treat as inserting a new key
                del self._store[key]
                self._insert_new(key, value, expires_at)
            else:
                # Live: overwrite, reset TTL, mark MRU
                self._store[key] = (value, expires_at)
                self._store.move_to_end(key)
        else:
            self._insert_new(key, value, expires_at)

    def get(self, key: Any, default: Any = None) -> Any:
        if key not in self._store:
            return default
        value, expires_at = self._store[key]
        if self._is_expired(expires_at):
            del self._store[key]
            return default
        self._store.move_to_end(key)
        return value

    def peek(self, key: Any, default: Any = None) -> Any:
        if key not in self._store:
            return default
        value, expires_at = self._store[key]
        if self._is_expired(expires_at):
            del self._store[key]
            return default
        return value

    def delete(self, key: Any) -> bool:
        if key not in self._store:
            return False
        _, expires_at = self._store[key]
        if self._is_expired(expires_at):
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

    def __contains__(self, key: object) -> bool:
        if key not in self._store:
            return False
        _, expires_at = self._store[key]
        if self._is_expired(expires_at):
            del self._store[key]
            return False
        return True
