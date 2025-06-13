"""Caching utilities for the indexer."""

import logging
import time
from decimal import Decimal
from threading import RLock
from typing import Any, Dict, List, Optional, TypeVar, Union

from config import (
    ADDRESS_CACHE_SIZE,
    BALANCE_CACHE_SIZE,
    BLOCK_CACHE_SIZE,
    COLLECTION_CACHE_SIZE,
    DEPLOYMENT_CACHE_SIZE,
    MARKET_DATA_CACHE_SIZE,
    PRICE_CACHE_SIZE,
    SRC101_DEPLOY_CACHE_SIZE,
    STAMP_CACHE_SIZE,
    SUBASSET_CACHE_SIZE,
    TOTAL_MINTED_CACHE_SIZE,
)
from index_core.cache_types import LRUCache
from index_core.memory_manager import memory_manager
from index_core.stamp_types import DeployResult, SRC101DeployResult

logger = logging.getLogger(__name__)
D = Decimal
T = TypeVar("T")

# Type alias for cache statistics
CacheStats = Dict[str, Dict[str, Union[int, float]]]


class CacheManager:
    """Manages multiple caches and their memory usage."""

    def __init__(self) -> None:
        """Initialize the cache manager and create default caches."""
        logger.info("Initializing CacheManager")
        self._caches: Dict[str, LRUCache[Any]] = {}
        self._backend_instance: Optional[Any] = None
        self._last_stats_log: float = 0.0
        self._stats_log_interval: float = 300.0  # Log stats every 5 minutes
        self._lock = RLock()  # Use RLock instead of Lock for reentrant locking

        # Initialize default caches without holding the main lock
        self._init_default_caches()
        logger.debug(f"CacheManager initialized with caches: {list(self._caches.keys())}")

    def _init_default_caches(self) -> None:
        """Initialize all default caches."""
        logger.info("Starting default cache initialization")
        try:
            # Create each cache first with explicit typing
            caches_to_register: list[tuple[str, LRUCache[Any]]] = [
                ("balance", LRUCache[D](max_size=BALANCE_CACHE_SIZE)),
                ("total_minted", LRUCache[D](max_size=TOTAL_MINTED_CACHE_SIZE)),
                ("deploy", LRUCache[DeployResult](max_size=DEPLOYMENT_CACHE_SIZE)),
                ("block", LRUCache[Any](max_size=BLOCK_CACHE_SIZE)),
                ("stamp", LRUCache[int](max_size=STAMP_CACHE_SIZE)),
                ("reissue", LRUCache[bool](max_size=DEPLOYMENT_CACHE_SIZE)),
                ("subasset", LRUCache[str](max_size=SUBASSET_CACHE_SIZE)),
                ("collection", LRUCache[str](max_size=COLLECTION_CACHE_SIZE)),
                ("price", LRUCache[Optional[Dict[int, Any]]](max_size=PRICE_CACHE_SIZE)),
                ("src101_deploy", LRUCache[SRC101DeployResult](max_size=SRC101_DEPLOY_CACHE_SIZE)),
                ("address", LRUCache[str](max_size=ADDRESS_CACHE_SIZE)),
                ("market_data", LRUCache[Any](max_size=MARKET_DATA_CACHE_SIZE)),
            ]

            # Register each cache with minimal locking
            for name, cache in caches_to_register:
                logger.debug(f"Registering cache: {name}")
                self.register_cache(name, cache)

            # Log cache details
            for name, cache in self._caches.items():
                logger.debug(
                    f"  - Cache '{name}' initialized (type: {type(cache).__name__}, maxsize: {getattr(cache, 'maxsize', 'N/A')})"
                )

            # Log successful initialization
            logger.debug(f"Successfully initialized all default caches: {list(self._caches.keys())}")
        except Exception as e:
            logger.error(f"Error during CacheManager initialization: {e}")
            raise

    def register_cache(self, name: str, cache: LRUCache[Any]) -> None:
        """Register a cache for management."""
        try:
            # Quick check without lock first
            existing_cache = self._caches.get(name)
            if existing_cache is not None and existing_cache.max_size == cache.max_size:
                logger.debug(f"Cache '{name}' already registered with same size")
                return

            # Only lock for the actual registration
            with self._lock:
                # Re-check after acquiring lock
                existing_cache = self._caches.get(name)
                if existing_cache is not None:
                    if existing_cache.max_size == cache.max_size:
                        logger.debug(f"Cache '{name}' already registered with same size")
                        return
                    logger.warning(
                        f"Re-registering cache '{name}' with different size: {cache.max_size} "
                        f"(was {existing_cache.max_size})"
                    )
                    existing_cache.clear()
                    memory_manager.unregister_cache(name)

                # Register the new cache
                self._caches[name] = cache
                memory_manager.register_cache(name, cache)
                logger.debug(f"Registered cache '{name}' with max_size={cache.max_size}")
        except Exception as e:
            logger.error(f"Error registering cache '{name}': {e}")

    def register_backend(self, backend_instance: Any) -> None:
        """Register backend instance for its caches."""
        self._backend_instance = backend_instance
        logger.info(
            "Registered backend caches with sizes: raw_tx=%d, deserialized_tx=%d",
            backend_instance.raw_transactions_cache.max_size,
            backend_instance.deserialized_tx_cache.max_size,
        )

    def clear_all(self) -> None:
        """Clear all registered caches and backend caches."""
        with self._lock:
            logger.info("Starting cache clear operation")
            # Clear registered LRU caches
            for name, cache in self._caches.items():
                logger.info(f"Clearing cache '{name}' (current_size={len(cache)}, hits={cache.hits}, misses={cache.misses})")
                cache.clear()

            # Clear backend caches if registered
            if self._backend_instance is not None:
                logger.info(
                    "Clearing backend caches (raw_tx_size=%d, deserialized_tx_size=%d)",
                    len(self._backend_instance.raw_transactions_cache),
                    len(self._backend_instance.deserialized_tx_cache),
                )
                self._backend_instance.raw_transactions_cache.clear()
                self._backend_instance.deserialized_tx_cache.clear()
            logger.info("Completed cache clear operation")

    def get_stats(self) -> CacheStats:
        """Get detailed statistics about registered caches."""
        with self._lock:
            stats: CacheStats = {}
            for name, cache in self._caches.items():
                hit_ratio = round(cache.hits / (cache.hits + cache.misses) * 100, 2) if (cache.hits + cache.misses) > 0 else 0
                stats[name] = {
                    "size": len(cache),
                    "max_size": cache.max_size,
                    "hits": cache.hits,
                    "misses": cache.misses,
                    "hit_ratio": hit_ratio,
                }
            logger.debug(f"Cache stats: {stats}")
            return stats

    def log_cache_stats(self) -> None:
        """Log statistics about all registered caches."""
        current_time = time.time()
        if current_time - self._last_stats_log >= self._stats_log_interval:
            stats = self.get_stats()
            for cache_name, cache_stats in stats.items():
                logger.info(
                    f"Cache '{cache_name}' stats: "
                    f"size={cache_stats['size']}/{cache_stats['max_size']}, "
                    f"hits={cache_stats['hits']}, misses={cache_stats['misses']}, "
                    f"hit_ratio={cache_stats['hit_ratio']}%"
                )
            self._last_stats_log = current_time

    def check_memory_pressure(self) -> None:
        """Check memory pressure and clear caches if needed."""
        logger.debug("Checking memory pressure")
        memory_manager.clear_caches_if_needed()

    def get_cache(self, name: str) -> Optional[LRUCache[Any]]:
        """Retrieve a cache by name."""
        # Try without lock first
        cache = self._caches.get(name)
        if cache is not None:
            return cache

        # If not found, try with lock and reinitialization
        with self._lock:
            cache = self._caches.get(name)
            if cache is None:
                logger.warning(f"Cache '{name}' not found. Available caches: {list(self._caches.keys())}")
                try:
                    logger.info("Attempting to reinitialize default caches")
                    self._init_default_caches()
                    cache = self._caches.get(name)
                    if cache is not None:
                        logger.info(f"Successfully reinitialized cache '{name}'")
                    else:
                        logger.error(f"Cache '{name}' still not found after reinitialization")
                except Exception as e:
                    logger.error(f"Failed to reinitialize caches: {e}")
            return cache

    def set_cache_value(self, cache_name: str, key: str, value: Any) -> None:
        """Set a value in a specific cache."""
        with self._lock:
            cache = self.get_cache(cache_name)
            if cache is not None:
                try:
                    self.check_memory_pressure()
                    cache.set(key, value)
                    logger.debug(
                        f"Set value in cache '{cache_name}' for key '{key}' (cache_size={len(cache)}, hits={cache.hits}, misses={cache.misses})"
                    )
                except Exception as e:
                    logger.error(f"Error setting cache value: {e}")
            else:
                logger.error(
                    f"Failed to set value: cache '{cache_name}' not found. Available caches: {list(self._caches.keys())}"
                )

    def get_cache_value(self, cache_name: str, key: str) -> Optional[Any]:
        """Get a value from a specific cache."""
        with self._lock:
            cache = self.get_cache(cache_name)
            if cache is not None:
                try:
                    value = cache.get(key)
                    if value is not None:
                        logger.debug(f"Cache hit in '{cache_name}' for key '{key}' (hits={cache.hits}, misses={cache.misses})")
                    else:
                        logger.debug(
                            f"Cache miss in '{cache_name}' for key '{key}' (hits={cache.hits}, misses={cache.misses})"
                        )
                    return value
                except Exception as e:
                    logger.error(f"Error getting cache value: {e}")
                    return None
            logger.error(f"Failed to get value: cache '{cache_name}' not found. Available caches: {list(self._caches.keys())}")
            return None

    def invalidate_cache_entry(self, cache_name: str, key: str) -> None:
        """Invalidate a specific cache entry."""
        cache = self.get_cache(cache_name)
        if cache and key in cache:  # Use 'in' operator instead of contains()
            logger.debug(f"Invalidating entry in cache '{cache_name}' for key '{key}'")
            cache.invalidate(key)
        elif cache:
            logger.debug(f"No entry to invalidate in cache '{cache_name}' for key '{key}'")

    def invalidate_cache_entries(self, cache_name: str, keys: List[str]) -> None:
        """
        Invalidate multiple cache entries efficiently.

        Args:
            cache_name: Name of the cache to invalidate entries from
            keys: List of cache keys to invalidate
        """
        with self._lock:
            cache = self.get_cache(cache_name)
            if cache:
                for key in keys:
                    if key in cache:
                        logger.debug(f"Invalidating entry in cache '{cache_name}' for key '{key}'")
                        cache.invalidate(key)


# Global instance
cache_manager = CacheManager()


def clear_all_caches() -> None:
    """Global function to clear all caches in the system."""
    cache_manager.clear_all()
