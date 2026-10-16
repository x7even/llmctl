"""A fixed-capacity, per-entry-TTL, least-recently-used cache (stdlib only)."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Callable


class TTLCache:
    """LRU cache with per-entry time-to-live, deterministic under an injected clock."""

    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not (default_ttl > 0):
            raise ValueError("default_ttl must be > 0")

        self._capacity: int = capacity
        self._default_ttl: float = default_ttl
        self._clock: Callable[[], float] = clock
        # OrderedDict preserves insertion order: first = LRU, last = MRU.
        # Each value is a tuple (value, expiry_time).
        self._data: OrderedDict = OrderedDict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_expired(self, expiry: float) -> bool:
        return self._clock() >= expiry

    def _purge_expired(self) -> None:
        now = self._clock()
        to_remove = [k for k, (_, exp) in self._data.items() if now >= exp]
        for k in to_remove:
            del self._data[k]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, key, value, ttl: float | None = None) -> None:
        if ttl is not None and not (ttl > 0):
            raise ValueError("ttl must be > 0")

        effective_ttl: float = self._default_ttl if ttl is None else ttl
        now = self._clock()
        expiry = now + effective_ttl

        if key in self._data:
            _, old_expiry = self._data[key]
            if now >= old_expiry:
                # Expired – treat as a brand-new insertion.
                del self._data[key]
            else:
                # Overwrite a live entry: replace value, reset TTL, mark MRU.
                self._data[key] = (value, expiry)
                self._data.move_to_end(key)
                return

        # --- new-key path (key absent or previously expired) ---
        if len(self._data) >= self._capacity:
            self._purge_expired()
            if len(self._data) >= self._capacity:
                # Evict the single least-recently-used live entry.
                self._data.popitem(last=False)

        self._data[key] = (value, expiry)
        # New keys are appended at the tail (MRU) by OrderedDict;
        # move_to_end is a no-op here but keeps intent explicit.
        self._data.move_to_end(key)

    def get(self, key, default=None):
        if key not in self._data:
            return default
        value, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return default
        self._data.move_to_end(key)
        return value

    def peek(self, key, default=None):
        if key not in self._data:
            return default
        value, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return default
        return value

    def delete(self, key) -> bool:
        if key not in self._data:
            return False
        _, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return False
        del self._data[key]
        return True

    def keys(self) -> list:
        self._purge_expired()
        return list(self._data.keys())

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._data)

    def __contains__(self, key) -> bool:
        if key not in self._data:
            return False
        _, expiry = self._data[key]
        return not self._is_expired(expiry)
