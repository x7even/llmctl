import time
from collections import OrderedDict
from typing import Any, Callable


class TTLCache:
    def __init__(
        self,
        capacity: int,
        default_ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not isinstance(default_ttl, (int, float)) or isinstance(default_ttl, bool) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")

        self._capacity = capacity
        self._default_ttl = default_ttl
        self._clock = clock
        # Maps key -> (value, expiry_time)
        self._store: "OrderedDict[Any, tuple[Any, float]]" = OrderedDict()

    def _is_expired(self, expiry: float) -> bool:
        return self._clock() >= expiry

    def _purge_expired(self) -> None:
        now = self._clock()
        expired_keys = [k for k, (_, exp) in self._store.items() if now >= exp]
        for k in expired_keys:
            del self._store[k]

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or ttl <= 0:
                raise ValueError("ttl must be > 0")
            effective_ttl = ttl
        else:
            effective_ttl = self._default_ttl

        now = self._clock()
        expiry = now + effective_ttl

        # Check if key exists and is live
        if key in self._store:
            _, old_expiry = self._store[key]
            if now < old_expiry:
                # Live entry: overwrite value, reset TTL, mark MRU
                self._store[key] = (value, expiry)
                self._store.move_to_end(key)
                return
            else:
                # Expired entry: treat as new key insertion
                del self._store[key]

        # New key insertion
        # Purge expired entries first
        self._purge_expired()

        if len(self._store) >= self._capacity:
            # Evict LRU
            self._store.popitem(last=False)

        self._store[key] = (value, expiry)

    def get(self, key: Any, default: Any = None) -> Any:
        if key not in self._store:
            return default
        value, expiry = self._store[key]
        if self._clock() >= expiry:
            del self._store[key]
            return default
        self._store.move_to_end(key)
        return value

    def peek(self, key: Any, default: Any = None) -> Any:
        if key not in self._store:
            return default
        value, expiry = self._store[key]
        if self._clock() >= expiry:
            del self._store[key]
            return default
        return value

    def delete(self, key: Any) -> bool:
        if key not in self._store:
            return False
        value, expiry = self._store[key]
        if self._clock() >= expiry:
            del self._store[key]
            return False
        del self._store[key]
        return True

    def keys(self) -> list:
        self._purge_expired()
        return list(self._store.keys())

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._store)

    def __contains__(self, key: Any) -> bool:
        if key not in self._store:
            return False
        _, expiry = self._store[key]
        if self._clock() >= expiry:
            del self._store[key]
            return False
        return True
