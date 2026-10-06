from collections import OrderedDict
from typing import Any, Callable
import time


class TTLCache:
    """A fixed-capacity cache with per-entry time-to-live and LRU eviction."""

    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool):
            raise ValueError("capacity must be an int >= 1")
        if capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not isinstance(default_ttl, (int, float)) or isinstance(default_ttl, bool):
            raise ValueError("default_ttl must be > 0")
        if default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")

        self._capacity = capacity
        self._default_ttl = float(default_ttl)
        self._clock = clock
        # OrderedDict: key -> (value, expiry_time)
        # Order is LRU (front) to MRU (back)
        self._data: "OrderedDict[Any, tuple[Any, float]]" = OrderedDict()

    def _purge_expired(self) -> None:
        """Remove all expired entries from the cache."""
        now = self._clock()
        expired_keys = [
            k for k, (_, expiry) in self._data.items() if now >= expiry
        ]
        for k in expired_keys:
            del self._data[k]

    def _is_expired(self, expiry: float) -> bool:
        return self._clock() >= expiry

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool):
                raise ValueError("ttl must be > 0")
            if ttl <= 0:
                raise ValueError("ttl must be > 0")
            effective_ttl = float(ttl)
        else:
            effective_ttl = self._default_ttl

        now = self._clock()
        expiry = now + effective_ttl

        # Check if key exists and is live
        if key in self._data:
            _, existing_expiry = self._data[key]
            if not self._is_expired(existing_expiry):
                # Overwrite existing live key: replace value, reset TTL, mark MRU
                self._data[key] = (value, expiry)
                self._data.move_to_end(key)
                return
            else:
                # Expired: treat as new key, remove it
                del self._data[key]

        # Inserting a new key
        # First purge all expired entries
        self._purge_expired()

        if len(self._data) >= self._capacity:
            # Evict LRU entry
            self._data.popitem(last=False)

        self._data[key] = (value, expiry)

    def get(self, key: Any, default: Any = None) -> Any:
        if key not in self._data:
            return default

        value, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return default

        # Mark as most-recently-used
        self._data.move_to_end(key)
        return value

    def peek(self, key: Any, default: Any = None) -> Any:
        if key not in self._data:
            return default

        value, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return default

        return value

    def delete(self, key: Any) -> bool:
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

    def __contains__(self, key: Any) -> bool:
        if key not in self._data:
            return False
        _, expiry = self._data[key]
        if self._is_expired(expiry):
            del self._data[key]
            return False
        return True
