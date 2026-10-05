import time
from collections import OrderedDict
from typing import Callable, Optional

_INF = float("inf")


class _Entry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value, expires_at):
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

        self._validate_positive(default_ttl, "default_ttl")

        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        self._entries: OrderedDict = OrderedDict()

    @staticmethod
    def _validate_positive(value, name: str) -> None:
        try:
            ok = bool(value > 0)
        except Exception:
            raise ValueError(f"{name} must be a positive number") from None

        if not ok:
            raise ValueError(f"{name} must be a positive number")

    def _is_expired(self, entry: _Entry, now: float) -> bool:
        if entry.expires_at is None:
            return False
        return now >= entry.expires_at

    def _purge_expired(self, now: float) -> None:
        for key in list(self._entries):
            entry = self._entries.get(key)
            if entry is not None and self._is_expired(entry, now):
                self._entries.pop(key)

    def _make_entry(self, value, ttl: float, now: float) -> _Entry:
        expires_at = None if ttl == _INF else now + ttl
        return _Entry(value, expires_at)

    def put(self, key, value, ttl: Optional[float] = None) -> None:
        if ttl is not None:
            self._validate_positive(ttl, "ttl")

        now = self._clock()
        entry = self._entries.get(key)

        if entry is not None and not self._is_expired(entry, now):
            effective_ttl = ttl if ttl is not None else self._default_ttl
            entry.value = value
            entry.expires_at = None if effective_ttl == _INF else now + effective_ttl
            self._entries.move_to_end(key)
            return

        needs_space = len(self._entries) >= self._capacity

        if entry is not None:
            self._entries.pop(key)

        if needs_space:
            self._purge_expired(now)
            if len(self._entries) >= self._capacity:
                self._entries.popitem(last=False)

        effective_ttl = ttl if ttl is not None else self._default_ttl
        self._entries[key] = self._make_entry(value, effective_ttl, now)

    def get(self, key, default=None):
        entry = self._entries.get(key)
        if entry is None:
            return default

        now = self._clock()
        if self._is_expired(entry, now):
            self._entries.pop(key)
            return default

        self._entries.move_to_end(key)
        return entry.value

    def peek(self, key, default=None):
        entry = self._entries.get(key)
        if entry is None:
            return default

        now = self._clock()
        if self._is_expired(entry, now):
            self._entries.pop(key)
            return default

        return entry.value

    def delete(self, key) -> bool:
        entry = self._entries.get(key)
        if entry is None:
            return False

        now = self._clock()
        if self._is_expired(entry, now):
            self._entries.pop(key)
            return False

        self._entries.pop(key)
        return True

    def keys(self) -> list:
        now = self._clock()
        self._purge_expired(now)
        return list(self._entries.keys())

    def __len__(self) -> int:
        now = self._clock()
        self._purge_expired(now)
        return len(self._entries)

    def __contains__(self, key) -> bool:
        entry = self._entries.get(key)
        if entry is None:
            return False

        now = self._clock()
        if self._is_expired(entry, now):
            self._entries.pop(key)
            return False

        return True
