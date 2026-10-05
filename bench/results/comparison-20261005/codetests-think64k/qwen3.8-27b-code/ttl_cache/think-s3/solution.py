import time
from collections import OrderedDict
from typing import Any, Callable, Optional

_INF = float("inf")


class _Entry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, expires_at: Optional[float]) -> None:
        self.value = value
        self.expires_at = expires_at


class TTLCache:
    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an integer >= 1")
        if not self._is_valid_ttl(default_ttl):
            raise ValueError("default_ttl must be > 0")

        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        self._data = OrderedDict()

    @staticmethod
    def _is_valid_ttl(ttl: Any) -> bool:
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)):
            return False
        return ttl > 0

    @staticmethod
    def _expires_at(now: float, ttl: float) -> Optional[float]:
        if ttl == _INF:
            return None
        return now + ttl

    @staticmethod
    def _is_live(entry: _Entry, now: float) -> bool:
        return entry.expires_at is None or now < entry.expires_at

    def _resolve_ttl(self, ttl: Optional[float]) -> float:
        if ttl is None:
            return self._default_ttl
        if not self._is_valid_ttl(ttl):
            raise ValueError("ttl must be > 0")
        return ttl

    def _purge(self, now: float) -> None:
        if not self._data:
            return
        expired = [
            key
            for key, entry in self._data.items()
            if not self._is_live(entry, now)
        ]
        for key in expired:
            del self._data[key]

    def _insert_new(self, key: Any, value: Any, ttl: float, now: float) -> None:
        self._purge(now)
        if len(self._data) >= self._capacity:
            self._data.popitem(last=False)
        self._data[key] = _Entry(value, self._expires_at(now, ttl))

    def put(self, key: Any, value: Any, ttl: Optional[float] = None) -> None:
        ttl = self._resolve_ttl(ttl)

        entry = self._data.get(key)
        if entry is None:
            now = self._clock()
            self._insert_new(key, value, ttl, now)
            return

        now = self._clock()
        if self._is_live(entry, now):
            self._data[key] = _Entry(value, self._expires_at(now, ttl))
            self._data.move_to_end(key)
        else:
            del self._data[key]
            self._insert_new(key, value, ttl, now)

    def get(self, key: Any, default: Any = None) -> Any:
        entry = self._data.get(key)
        if entry is None:
            return default

        now = self._clock()
        if not self._is_live(entry, now):
            del self._data[key]
            return default

        self._data.move_to_end(key)
        return entry.value

    def peek(self, key: Any, default: Any = None) -> Any:
        entry = self._data.get(key)
        if entry is None:
            return default

        now = self._clock()
        if not self._is_live(entry, now):
            del self._data[key]
            return default

        return entry.value

    def delete(self, key: Any) -> bool:
        entry = self._data.get(key)
        if entry is None:
            return False

        now = self._clock()
        if not self._is_live(entry, now):
            del self._data[key]
            return False

        del self._data[key]
        return True

    def keys(self) -> list:
        if not self._data:
            return []
        now = self._clock()
        self._purge(now)
        return list(self._data.keys())

    def __len__(self) -> int:
        if not self._data:
            return 0
        now = self._clock()
        self._purge(now)
        return len(self._data)

    def __contains__(self, key: Any) -> bool:
        entry = self._data.get(key)
        if entry is None:
            return False

        now = self._clock()
        if not self._is_live(entry, now):
            del self._data[key]
            return False

        return True
