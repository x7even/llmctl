from collections import OrderedDict
from typing import Callable, Any


class TTLCache:
    def __init__(self, capacity: int, default_ttl: float, clock: Callable[[], float] = None) -> None:
        if clock is None:
            import time
            clock = time.monotonic
        
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        if not isinstance(default_ttl, (int, float)) or default_ttl <= 0:
            raise ValueError("default_ttl must be > 0")
        
        self._capacity = capacity
        self._default_ttl = float(default_ttl)
        self._clock = clock
        # _store: OrderedDict[key -> (value, expiry_time)]
        # Order is LRU (left) to MRU (right)
        self._store: OrderedDict = OrderedDict()
    
    def _now(self) -> float:
        return self._clock()
    
    def _purge_expired(self) -> None:
        """Remove all expired entries from the cache."""
        now = self._now()
        expired_keys = []
        for key, (value, expiry) in self._store.items():
            if now >= expiry:
                expired_keys.append(key)
        for key in expired_keys:
            del self._store[key]
    
    def _is_expired(self, key: Any) -> bool:
        """Check if a specific key is expired. Assumes key exists in _store."""
        now = self._now()
        _, expiry = self._store[key]
        return now >= expiry
    
    def _move_to_end(self, key: Any) -> None:
        """Move key to the end (MRU position)."""
        self._store.move_to_end(key)
    
    def put(self, key, value, ttl: float | None = None) -> None:
        if ttl is not None:
            if not isinstance(ttl, (int, float)) or ttl <= 0:
                raise ValueError("ttl must be > 0")
            entry_ttl = float(ttl)
        else:
            entry_ttl = self._default_ttl
        
        now = self._now()
        expiry = now + entry_ttl
        
        # If key exists, check if it's expired
        if key in self._store:
            if self._is_expired(key):
                # Treat as new key: remove expired entry first
                del self._store[key]
                # Now proceed as insertion of new key
                self._insert_new(key, value, expiry)
            else:
                # Overwrite existing live key
                self._store[key] = (value, expiry)
                self._move_to_end(key)
        else:
            # New key
            self._insert_new(key, value, expiry)
    
    def _insert_new(self, key: Any, value: Any, expiry: float) -> None:
        """Insert a new key, handling eviction if necessary."""
        # First, purge all expired entries
        self._purge_expired()
        
        # If still at capacity, evict LRU
        if len(self._store) >= self._capacity:
            # Evict the first item (LRU)
            self._store.popitem(last=False)
        
        # Insert new key at the end (MRU)
        self._store[key] = (value, expiry)
    
    def get(self, key, default=None):
        if key not in self._store:
            return default
        
        if self._is_expired(key):
            del self._store[key]
            return default
        
        # Live entry: return value and mark as MRU
        value, _ = self._store[key]
        self._move_to_end(key)
        return value
    
    def peek(self, key, default=None):
        if key not in self._store:
            return default
        
        if self._is_expired(key):
            del self._store[key]
            return default
        
        # Live entry: return value without changing recency
        value, _ = self._store[key]
        return value
    
    def delete(self, key) -> bool:
        if key not in self._store:
            return False
        
        if self._is_expired(key):
            del self._store[key]
            return False
        
        # Live entry: remove it
        del self._store[key]
        return True
    
    def keys(self) -> list:
        # Purge expired entries first
        self._purge_expired()
        # Return keys from LRU (left) to MRU (right)
        return list(self._store.keys())
    
    def __len__(self) -> int:
        # Purge expired entries first
        self._purge_expired()
        return len(self._store)
    
    def __contains__(self, key) -> bool:
        if key not in self._store:
            return False
        
        if self._is_expired(key):
            del self._store[key]
            return False
        
        return True
