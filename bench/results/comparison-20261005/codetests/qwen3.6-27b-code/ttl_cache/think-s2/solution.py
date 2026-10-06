import time
from collections import OrderedDict
from typing import Callable

class TTLCache:
    def __init__(self, capacity: int, default_ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not isinstance(default_ttl, (int, float)) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        self._capacity = capacity
        self._default_ttl = float(default_ttl)
        self._clock = clock
        self._data = OrderedDict()
        self._expires = {}

    def _purge_expired(self) -> None:
        now = self._clock()
        to_remove = [k for k in self._data if self._expires[k] <= now]
        for k in to_remove:
            del self._data[k]
            del self._expires[k]

    def put(self, key, value, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or ttl <= 0:
                raise ValueError("ttl must be > 0")
            ttl_val = float(ttl)
        else:
            ttl_val = self._default_ttl

        now = self._clock()
        expiry = now + ttl_val

        if key in self._data:
            if self._expires[key] <= now:
                del self._data[key]
                del self._expires[key]
            else:
                self._data[key] = value
                self._expires[key] = expiry
                self._data.move_to_end(key)
                return

        self._purge_expired()

        if len(self._data) >= self._capacity:
            evicted_key, _ = self._data.popitem(last=False)
            del self._expires[evicted_key]

        self._data[key] = value
        self._expires[key] = expiry

    def get(self, key, default=None):
        now = self._clock()
        if key in self._data:
            if self._expires[key] <= now:
                del self._data[key]
                del self._expires[key]
                return default
            val = self._data[key]
            self._data.move_to_end(key)
            return val
        return default

    def peek(self, key, default=None):
        now = self._clock()
        if key in self._data:
            if self._expires[key] <= now:
                del self._data[key]
                del self._expires[key]
                return default
            return self._data[key]
        return default

    def delete(self, key) -> bool:
        now = self._clock()
        if key in self._data:
            is_live = self._expires[key] > now
            del self._data[key]
            del self._expires[key]
            return is_live
        return False

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._data)

    def __contains__(self, key) -> bool:
        if key in self._data:
            now = self._clock()
            if self._expires[key] <= now:
                del self._data[key]
                del self._expires[key]
                return False
            return True
        return False

    def keys(self) -> list:
        self._purge_expired()
        return list(self._data.keys())
