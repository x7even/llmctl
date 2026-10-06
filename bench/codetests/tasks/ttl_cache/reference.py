"""Reference solution (used only to validate the hidden tests; never shown to models)."""
import time
from collections import OrderedDict


class TTLCache:
    def __init__(self, capacity, default_ttl, clock=time.monotonic):
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity")
        if not default_ttl > 0:
            raise ValueError("default_ttl")
        self._cap = capacity
        self._ttl = default_ttl
        self._clock = clock
        self._d = OrderedDict()  # key -> (value, expires_at); order: LRU -> MRU

    def _live(self, key):
        item = self._d.get(key)
        if item is None:
            return None
        if self._clock() >= item[1]:
            del self._d[key]
            return None
        return item

    def _purge(self):
        now = self._clock()
        for k in [k for k, (_, e) in self._d.items() if now >= e]:
            del self._d[k]

    def put(self, key, value, ttl=None):
        if ttl is not None and not ttl > 0:
            raise ValueError("ttl")
        ttl = self._ttl if ttl is None else ttl
        if self._live(key) is not None:
            self._d.move_to_end(key)
        else:
            self._purge()
            while len(self._d) >= self._cap:
                self._d.popitem(last=False)
        self._d[key] = (value, self._clock() + ttl)
        self._d.move_to_end(key)

    def get(self, key, default=None):
        item = self._live(key)
        if item is None:
            return default
        self._d.move_to_end(key)
        return item[0]

    def peek(self, key, default=None):
        item = self._live(key)
        return default if item is None else item[0]

    def delete(self, key):
        if self._live(key) is None:
            return False
        del self._d[key]
        return True

    def keys(self):
        self._purge()
        return list(self._d.keys())

    def __len__(self):
        self._purge()
        return len(self._d)

    def __contains__(self, key):
        return self._live(key) is not None
