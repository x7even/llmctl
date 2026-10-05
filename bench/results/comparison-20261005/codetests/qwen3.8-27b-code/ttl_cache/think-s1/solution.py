from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable

_INF = float("inf")


def _validate_ttl(ttl: float) -> None:
    if isinstance(ttl, bool) or not isinstance(ttl, (int, float)):
        raise ValueError("ttl must be a number > 0")
    if not ttl > 0:
        raise ValueError("ttl must be > 0")


class TTLCache:
    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        _validate_ttl(default_ttl)

        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        self._entries: OrderedDict[Any, tuple[Any, float, bool]] = OrderedDict()

    def _purge_expired(self, now: float) -> None:
        entries = self._entries
        for key in list(entries):
            _, expiry, infinite = entries[key]
            if not infinite and expiry <= now:
                del entries[key]

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        if ttl is None:
            effective_ttl = self._default_ttl
        else:
            _validate_ttl(ttl)
            effective_ttl = ttl

        now = self._clock()
        self._purge_expired(now)

        infinite = effective_ttl == _INF
        expiry = _INF if infinite else now + effective_ttl
        entry = (value, expiry, infinite)

        if key in self._entries:
            self._entries[key] = entry
            self._entries.move_to_end(key)
        else:
            if len(self._entries) >= self._capacity:
                self._entries.popitem(last=False)
            self._entries[key] = entry

    def get(self, key: Any, default: Any = None) -> Any:
        now = self._clock()
        self._purge_expired(now)

        if key in self._entries:
            value = self._entries[key][0]
            self._entries.move_to_end(key)
            return value
        return default

    def peek(self, key: Any, default: Any = None) -> Any:
        now = self._clock()
        self._purge_expired(now)

        if key in self._entries:
            return self._entries[key][0]
        return default

    def delete(self, key: Any) -> bool:
        now = self._clock()
        self._purge_expired(now)

        if key in self._entries:
            del self._entries[key]
            return True
        return False

    def keys(self) -> list:
        now = self._clock()
        self._purge_expired(now)
        return list(self._entries.keys())

    def __len__(self) -> int:
        now = self._clock()
        self._purge_expired(now)
        return len(self._entries)

    def __contains__(self, key: Any) -> bool:
        now = self._clock()
        self._purge_expired(now)
        return key in self._entries
