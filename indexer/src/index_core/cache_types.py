"""Cache type definitions."""

import logging
import threading
from collections import OrderedDict
from typing import Generic, Iterator, List, Optional, Tuple, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class LRUCache(Generic[T]):
    """Thread-safe LRU cache implementation with logging and metrics."""

    def __init__(self, max_size: int = 1000):
        """Initialize the cache with a maximum size."""
        self.max_size = max_size
        self.cache: OrderedDict[str, T] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[T]:
        """Get value from cache, moving it to end if found."""
        with self._lock:
            if key not in self.cache:
                self.misses += 1
                logger.debug(f"Cache miss for key: {key}")
                return None
            self.hits += 1
            self.cache.move_to_end(key)
            logger.debug(f"Cache hit for key: {key}")
            return self.cache[key]

    def set(self, key: str, value: T) -> None:
        """Set value in cache, removing least recently used if at capacity."""
        with self._lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            if len(self.cache) > self.max_size:
                evicted_key, _ = self.cache.popitem(last=False)
                logger.debug(f"Evicted key: {evicted_key} due to cache capacity")

    def invalidate(self, key: str) -> None:
        """Remove a specific key from the cache."""
        with self._lock:
            if key in self.cache:
                logger.debug(f"Invalidating key: {key}")
            self.cache.pop(key, None)

    def clear(self) -> None:
        """Clear all items from the cache."""
        with self._lock:
            logger.debug("Clearing all cache entries")
            self.cache.clear()

    def __iter__(self) -> Iterator[str]:
        """Return an iterator over the cache keys."""
        with self._lock:
            return iter(list(self.cache.keys()))

    def __len__(self) -> int:
        """Return the number of items in the cache."""
        return len(self.cache)

    def items(self) -> List[Tuple[str, T]]:
        """Return a list of all (key, value) pairs in the cache."""
        with self._lock:
            return list(self.cache.items())

    def keys(self) -> List[str]:
        """Return a list of all keys in the cache."""
        with self._lock:
            return list(self.cache.keys())

    def values(self) -> List[T]:
        """Return a list of all values in the cache."""
        with self._lock:
            return list(self.cache.values())

    def contains(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        with self._lock:
            return key in self.cache

    def get_metrics(self) -> Tuple[int, int]:
        """Return cache hit and miss metrics."""
        return self.hits, self.misses
