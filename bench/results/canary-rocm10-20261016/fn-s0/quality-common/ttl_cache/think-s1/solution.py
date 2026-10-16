"""A fixed-capacity cache with per-entry TTL and LRU eviction (stdlib only)."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable, Hashable


class TTLCache:
    """Least-recently-used cache with per-entry time-to-live.

    Parameters
    ----------
    capacity:
        Maximum number of *live* entries the cache may hold (int >= 1).
    default_ttl:
        Default time-to-live in seconds for entries whose *put* call omits *ttl*
        (must be > 0; ``float('inf')`` means never expires).
    clock:
        Zero-argument callable returning the current time as a float.
        Defaults to ``time.monotonic``; tests inject a fake clock.
    """

    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError(f"capacity must be an int >= 1, got {capacity!r}")
        if not (default_ttl > 0):
            raise ValueError(f"default_ttl must be > 0, got {default_ttl!r}")

        self._capacity: int = capacity
        self._default_ttl: float = default_ttl
        self._clock: Callable[[], float] = clock
        # OrderedDict keeps LRU order: first item = least recently used.
        # Values are (value, expiry_time) tuples.
        self._data: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_expired(self, expiry: float, now: float) -> bool:
        """An entry is expired when *now >= expiry*."""
        return now >= expiry

    def _purge_expired(self, now: float) -> None:
        """Remove every expired entry from the cache."""
        expired_keys = [
            k for k, (_, exp) in self._data.items() if self._is_expired(exp, now)
        ]
        for k in expired_keys:
            del self._data[k]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, key: Hashable, value: Any, ttl: float | None = None) -> None:
        """Insert or overwrite *key*.

        If *ttl* is ``None`` the cache's ``default_ttl`` is used.
        A non-None *ttl* must be > 0 (``float('inf')`` is allowed).
        """
        # --- validate per-entry ttl (before any mutation) ---
        if ttl is not None:
            if not (ttl > 0):
                raise ValueError(f"ttl must be > 0, got {ttl!r}")
            effective_ttl = ttl
        else:
            effective_ttl = self._default_ttl

        now = self._clock()
        expiry = now + effective_ttl

        if key in self._data:
            _, old_expiry = self._data[key]
            if not self._is_expired(old_expiry, now):
                # Overwrite a *live* entry: replace value, reset TTL, mark MRU.
                self._data[key] = (value, expiry)
                self._data.move_to_end(key)
                return
            # Key exists but is expired → treat as a fresh insert.
            del self._data[key]

        # --- new-key path: may need eviction ---
        # Purge all expired entries first.
        self._purge_expired(now)

        # If still at capacity, evict the single LRU live entry.
        if len(self._data) >= self._capacity:
            self._data.popitem(last=False)  # evict first (LRU)

        self._data[key] = (value, expiry)

    def get(self, key: Hashable, default: Any = None) -> Any:
        """Return the value for *key* if live, marking it MRU.

        Expired entries are removed.  TTL is *not* extended.
        """
        if key not in self._data:
            return default

        value, expiry = self._data[key]
        now = self._clock()

        if self._is_expired(expiry, now):
            del self._data[key]
            return default

        # Mark most-recently-used (does NOT reset TTL).
        self._data.move_to_end(key)
        return value

    def peek(self, key: Hashable, default: Any = None) -> Any:
        """Return the value for *key* if live, without changing recency."""
        if key not in self._data:
            return default

        value, expiry = self._data[key]
        now = self._clock()

        if self._is_expired(expiry, now):
            del self._data[key]
            return default

        return value

    def delete(self, key: Hashable) -> bool:
        """Remove *key*.  Returns ``True`` only if a *live* entry was removed."""
        if key not in self._data:
            return False

        _, expiry = self._data[key]
        now = self._clock()

        # Remove the entry regardless of liveness.
        del self._data[key]

        return not self._is_expired(expiry, now)

    def keys(self) -> list:
        """Live keys ordered LRU → MRU."""
        now = self._clock()
        self._purge_expired(now)
        return list(self._data.keys())

    def __len__(self) -> int:
        """Number of live entries (expired entries are purged first)."""
        now = self._clock()
        self._purge_expired(now)
        return len(self._data)

    def __contains__(self, key: Hashable) -> bool:
        """True only if *key* is present and live.  Does not change recency."""
        if key not in self._data:
            return False
        _, expiry = self._data[key]
        return not self._is_expired(expiry, self._clock())
