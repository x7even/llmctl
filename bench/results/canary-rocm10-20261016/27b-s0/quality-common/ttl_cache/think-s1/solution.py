"""A fixed-capacity TTL cache with LRU eviction and an injectable clock."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable


class TTLCache:
    """A least-recently-used cache with per-entry time-to-live.

    Deterministic under an injected clock (defaults to ``time.monotonic``).
    """

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
        self._capacity: int = capacity
        self._default_ttl: float = default_ttl
        self._clock: Callable[[], float] = clock
        # Maps key -> (value, absolute_expiry)
        # OrderedDict: first = LRU, last = MRU
        self._data: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_expired(self, expiry: float) -> bool:
        return self._clock() >= expiry

    def _purge_all_expired(self) -> None:
        now = self._clock()
        expired = [k for k, (_, exp) in self._data.items() if now >= exp]
        for k in expired:
            del self._data[k]

    def _purge_key_if_expired(self, key: Any) -> bool:
        """Remove *key* if present and expired.  Returns True if removed."""
        if key in self._data:
            _, exp = self._data[key]
            if self._clock() >= exp:
                del self._data[key]
                return True
        return False

    def _insert_new(self, key: Any, value: Any, expiry: float) -> None:
        self._purge_all_expired()
        if len(self._data) >= self._capacity:
            self._data.popitem(last=False)  # evict LRU
        self._data[key] = (value, expiry)   # appended at end → MRU

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or ttl <= 0:
                raise ValueError("ttl must be > 0")

        now = self._clock()
        effective_ttl: float = ttl if ttl is not None else self._default_ttl
        expiry: float = now + effective_ttl

        if key in self._data:
            _, existing_exp = self._data[key]
            if self._clock() >= existing_exp:
                # Expired → treat as a brand-new key
                del self._data[key]
                self._insert_new(key, value, expiry)
            else:
                # Live overwrite: replace value, reset TTL, mark MRU
                self._data[key] = (value, expiry)
                self._data.move_to_end(key)
        else:
            self._insert_new(key, value, expiry)

    def get(self, key: Any, default: Any = None) -> Any:
        if key in self._data:
            value, exp = self._data[key]
            if self._clock() >= exp:
                del self._data[key]
                return default
            self._data.move_to_end(key)  # mark MRU
            return value
        return default

    def peek(self, key: Any, default: Any = None) -> Any:
        if key in self._data:
            value, exp = self._data[key]
            if self._clock() >= exp:
                del self._data[key]
                return default
            return value  # no recency change
        return default

    def delete(self, key: Any) -> bool:
        if key in self._data:
            _, exp = self._data[key]
            if self._clock() >= exp:
                del self._data[key]
                return False
            del self._data[key]
            return True
        return False

    def keys(self) -> list:
        self._purge_all_expired()
        return list(self._data.keys())  # LRU → MRU

    def __len__(self) -> int:
        self._purge_all_expired()
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        if key in self._data:
            _, exp = self._data[key]
            if self._clock() >= exp:
                del self._data[key]
                return False
            return True
        return False
