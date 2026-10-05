from collections import OrderedDict
from typing import Callable, Any, Optional


class TTLCache:
    def __init__(self, capacity: int, default_ttl: float, clock: Callable[[], float] = None) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not isinstance(default_ttl, (int, float)) or isinstance(default_ttl, bool) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        if clock is None:
            import time
            clock = time.monotonic
        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        # key -> (value, expiry_time)
        self._data: "OrderedDict[Any, tuple[Any, float]]" = OrderedDict()

    def _purge_expired(self) -> None:
        now = self._clock()
        to_remove = []
        for key, (_, expiry) in self._data.items():
            if now >= expiry:
                to_remove.append(key)
        for key in to_remove:
            del self._data[key]

    def _is_expired(self, expiry: float) -> bool:
        return self._clock() >= expiry

    def put(self, key, value, ttl: Optional[float] = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or ttl <= 0:
                raise ValueError("ttl must be > 0")
        effective_ttl = self._default_ttl if ttl is None else ttl
        now = self._clock()
        expiry = now + effective_ttl

        # Check if key exists and is still live
        if key in self._data:
            _, existing_expiry = self._data[key]
            if not self._is_expired(existing_expiry):
                # Overwrite existing live key: reset TTL, mark MRU
                self._data[key] = (value, expiry)
                self._data.move_to_end(key)
                return
            else:
                # Expired: treat as new key, remove it first
                del self._data[key]

        # Inserting a new key
        self._purge_expired()

        if len(self._data) >= self._capacity:
            # Evict LRU
            self._data.popitem(last=False)

        self._data[key] = (value, expiry)

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
        if self._is_expired(expiry):
            del self._data[key]
            return False
        return True
