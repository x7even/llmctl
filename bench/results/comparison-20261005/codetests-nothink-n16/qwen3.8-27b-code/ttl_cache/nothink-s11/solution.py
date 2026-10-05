from collections import OrderedDict
from typing import Callable, Any, Optional
import time


class TTLCache:
    def __init__(self, capacity: int, default_ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool):
            raise ValueError("capacity must be an int")
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if not isinstance(default_ttl, (int, float)) or isinstance(default_ttl, bool):
            raise ValueError("default_ttl must be a number")
        if default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")

        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        # key -> (value, expiry_time)
        # OrderedDict preserves insertion order; we move_to_end on access to track LRU
        self._data: OrderedDict = OrderedDict()

    def _is_expired(self, expiry: float, now: Optional[float] = None) -> bool:
        if now is None:
            now = self._clock()
        return now >= expiry

    def _purge_expired(self) -> None:
        now = self._clock()
        expired_keys = []
        for key, (value, expiry) in self._data.items():
            if now >= expiry:
                expired_keys.append(key)
        for key in expired_keys:
            del self._data[key]

    def put(self, key, value, ttl: Optional[float] = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool):
                raise ValueError("ttl must be a number")
            if ttl <= 0:
                raise ValueError("ttl must be > 0")
            effective_ttl = ttl
        else:
            effective_ttl = self._default_ttl

        now = self._clock()
        expiry = now + effective_ttl

        # Check if key exists and is still live
        if key in self._data:
            _, existing_expiry = self._data[key]
            if not self._is_expired(existing_expiry, now):
                # Overwrite existing live key: reset TTL, mark MRU
                self._data[key] = (value, expiry)
                self._data.move_to_end(key)
                return
            else:
                # Expired: remove it, treat as new insertion
                del self._data[key]

        # New insertion
        # Purge expired entries first
        self._purge_expired()

        # If still at capacity, evict LRU
        if len(self._data) >= self._capacity:
            # Evict the least recently used (first item)
            self._data.popitem(last=False)

        self._data[key] = (value, expiry)

    def get(self, key, default=None):
        now = self._clock()
        if key in self._data:
            value, expiry = self._data[key]
            if now >= expiry:
                del self._data[key]
                return default
            else:
                self._data.move_to_end(key)
                return value
        return default

    def peek(self, key, default=None):
        now = self._clock()
        if key in self._data:
            value, expiry = self._data[key]
            if now >= expiry:
                del self._data[key]
                return default
            else:
                return value
        return default

    def delete(self, key) -> bool:
        now = self._clock()
        if key in self._data:
            value, expiry = self._data[key]
            if now >= expiry:
                del self._data[key]
                return False
            else:
                del self._data[key]
                return True
        return False

    def keys(self) -> list:
        self._purge_expired()
        return list(self._data.keys())

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._data)

    def __contains__(self, key) -> bool:
        now = self._clock()
        if key in self._data:
            value, expiry = self._data[key]
            if now >= expiry:
                del self._data[key]
                return False
            return True
        return False
