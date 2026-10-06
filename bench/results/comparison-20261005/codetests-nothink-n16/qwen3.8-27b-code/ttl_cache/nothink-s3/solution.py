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
        if not isinstance(default_ttl, (int, float)) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")

        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        # key -> (value, expires_at)
        self._store: "OrderedDict[Any, tuple[Any, float]]" = OrderedDict()

    def _now(self) -> float:
        return self._clock()

    def _is_expired(self, expires_at: float, now: float) -> bool:
        return now >= expires_at

    def _purge_expired(self, now: float) -> None:
        expired_keys = [
            k for k, (_, exp) in self._store.items() if self._is_expired(exp, now)
        ]
        for k in expired_keys:
            del self._store[k]

    def _purge_key_if_expired(self, key: Any, now: float) -> bool:
        """Remove key if present and expired. Return True if removed."""
        if key in self._store:
            _, exp = self._store[key]
            if self._is_expired(exp, now):
                del self._store[key]
                return True
        return False

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or ttl <= 0:
                raise ValueError("ttl must be > 0")
        now = self._now()

        # Check if key exists and is live
        if key in self._store:
            _, exp = self._store[key]
            if not self._is_expired(exp, now):
                # Overwrite existing live key
                effective_ttl = ttl if ttl is not None else self._default_ttl
                expires_at = now + effective_ttl
                self._store[key] = (value, expires_at)
                # Mark as most recently used
                self._store.move_to_end(key)
                return
            else:
                # Expired: remove it, treat as new insert
                del self._store[key]

        # New key insert (or overwrite of expired)
        # Purge expired entries first
        self._purge_expired(now)

        # If still at capacity, evict LRU
        if len(self._store) >= self._capacity:
            # Evict the least recently used (first item)
            lru_key, _ = self._store.popitem(last=False)

        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = now + effective_ttl
        self._store[key] = (value, expires_at)

    def get(self, key: Any, default: Any = None) -> Any:
        now = self._now()
        if key not in self._store:
            return default
        value, exp = self._store[key]
        if self._is_expired(exp, now):
            del self._store[key]
            return default
        # Mark as most recently used
        self._store.move_to_end(key)
        return value

    def peek(self, key: Any, default: Any = None) -> Any:
        now = self._now()
        if key not in self._store:
            return default
        value, exp = self._store[key]
        if self._is_expired(exp, now):
            del self._store[key]
            return default
        return value

    def delete(self, key: Any) -> bool:
        now = self._now()
        if key not in self._store:
            return False
        value, exp = self._store[key]
        if self._is_expired(exp, now):
            del self._store[key]
            return False
        del self._store[key]
        return True

    def keys(self) -> list:
        now = self._now()
        self._purge_expired(now)
        return list(self._store.keys())

    def __len__(self) -> int:
        now = self._now()
        self._purge_expired(now)
        return len(self._store)

    def __contains__(self, key: Any) -> bool:
        now = self._now()
        if key not in self._store:
            return False
        _, exp = self._store[key]
        if self._is_expired(exp, now):
            del self._store[key]
            return False
        return True
