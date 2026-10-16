"""A fixed-capacity TTL cache with LRU eviction.

Standard-library only.  Deterministic under an injected clock.
"""

from collections import OrderedDict
from typing import Any, Callable
import time


class TTLCache:
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
        # OrderedDict preserves insertion/access order: first = LRU, last = MRU
        self._data: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_expired(self, key: Any, now: float | None = None) -> bool:
        if now is None:
            now = self._clock()
        return now >= self._data[key][1]

    def _purge_expired(self, now: float | None = None) -> None:
        if now is None:
            now = self._clock()
        expired = [k for k, (_, exp) in self._data.items() if now >= exp]
        for k in expired:
            del self._data[k]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        if ttl is not None and not (ttl > 0):
            raise ValueError("ttl must be > 0")

        now = self._clock()
        effective_ttl = self._default_ttl if ttl is None else ttl
        expires_at = now + effective_ttl

        if key in self._data:
            if not self._is_expired(key, now):
                # Overwrite a live entry: replace value, reset TTL, mark MRU.
                self._data[key] = (value, expires_at)
                self._data.move_to_end(key)
                return
            # Expired entry – remove it and fall through to new-key path.
            del self._data[key]

        # --- New key insertion path ---
        # Discard all expired entries first.
        self._purge_expired(now)

        # Evict LRU if still at capacity.
        if len(self._data) >= self._capacity:
            self._data.popitem(last=False)

        self._data[key] = (value, expires_at)

    def get(self, key: Any, default: Any = None) -> Any:
        if key not in self._data:
            return default
        if self._is_expired(key):
            del self._data[key]
            return default
        self._data.move_to_end(key)
        return self._data[key][0]

    def peek(self, key: Any, default: Any = None) -> Any:
        if key not in self._data:
            return default
        if self._is_expired(key):
            del self._data[key]
            return default
        return self._data[key][0]

    def delete(self, key: Any) -> bool:
        if key not in self._data:
            return False
        if self._is_expired(key):
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

    def __contains__(self, key: Any) -> bool:
        if key not in self._data:
            return False
        return not self._is_expired(key)
