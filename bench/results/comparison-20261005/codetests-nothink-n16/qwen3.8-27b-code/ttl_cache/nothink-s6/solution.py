import time
from collections import OrderedDict
from typing import Any, Callable, Optional


class TTLCache:
    """A fixed-capacity cache with per-entry time-to-live and LRU eviction."""

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

        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        # key -> (value, expiry_time)
        self._data: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    def _purge_expired(self) -> None:
        """Remove all expired entries. Mutates self._data in place."""
        now = self._clock()
        expired_keys = [k for k, (_, exp) in self._data.items() if now >= exp]
        for k in expired_keys:
            del self._data[k]

    def _is_expired(self, key: Any) -> bool:
        """Check if the entry for key is expired. Assumes key exists in _data."""
        _, exp = self._data[key]
        return self._clock() >= exp

    def put(self, key: Any, value: Any, ttl: Optional[float] = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool):
                raise ValueError("ttl must be a number > 0")
            if ttl <= 0:
                raise ValueError("ttl must be > 0")

        now = self._clock()
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expiry = now + effective_ttl

        # Check if key exists and is live
        if key in self._data:
            _, existing_exp = self._data[key]
            if now < existing_exp:
                # Live entry: overwrite, reset TTL, mark MRU
                self._data[key] = (value, expiry)
                self._data.move_to_end(key)
                return
            else:
                # Expired entry: treat as new insertion (remove it first)
                del self._data[key]

        # New key insertion: may need eviction
        # First, purge all expired entries
        self._purge_expired()

        if len(self._data) >= self._capacity:
            # Evict LRU (first item in OrderedDict)
            self._data.popitem(last=False)

        self._data[key] = (value, expiry)

    def get(self, key: Any, default: Any = None) -> Any:
        if key not in self._data:
            return default

        _, exp = self._data[key]
        if self._clock() >= exp:
            del self._data[key]
            return default

        value, _ = self._data[key]
        self._data.move_to_end(key)
        return value

    def peek(self, key: Any, default: Any = None) -> Any:
        if key not in self._data:
            return default

        _, exp = self._data[key]
        if self._clock() >= exp:
            del self._data[key]
            return default

        value, _ = self._data[key]
        return value

    def delete(self, key: Any) -> bool:
        if key not in self._data:
            return False

        _, exp = self._data[key]
        if self._clock() >= exp:
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

        _, exp = self._data[key]
        if self._clock() >= exp:
            del self._data[key]
            return False

        return True
