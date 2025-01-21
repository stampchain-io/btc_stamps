"""Caching utilities for the indexer."""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, TypeVar

from index_core.cache_types import LRUCache
from index_core.memory_manager import memory_manager
from index_core.types import DeployResult

logger = logging.getLogger(__name__)
D = Decimal
T = TypeVar("T")


class CacheManager:
    """Manages multiple caches and their memory usage."""

    _caches: Dict[str, LRUCache[Any]]
    _backend_instance: Optional[Any]  # Type as Any to avoid circular import

    def __init__(self) -> None:
        """Initialize the cache manager."""
        self._caches = {}
        self._backend_instance = None

    def register_cache(self, name: str, cache: LRUCache[Any]) -> None:
        """Register a cache for management."""
        self._caches[name] = cache
        memory_manager.register_cache(name, cache)

    def register_backend(self, backend_instance: Any) -> None:
        """Register backend instance for its caches."""
        self._backend_instance = backend_instance
        logger.info("Registered backend caches")

    def clear_all(self) -> None:
        """Clear all registered caches and backend caches."""
        # Clear registered LRU caches
        for name, cache in self._caches.items():
            logger.info(f"Clearing cache: {name} (size={len(cache)})")
            cache.clear()

        # Clear backend caches if registered
        if self._backend_instance is not None:
            logger.info("Clearing backend caches")
            self._backend_instance.raw_transactions_cache.clear()
            self._backend_instance.deserialized_tx_cache.clear()

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about registered caches."""
        return {name: len(cache) for name, cache in self._caches.items()}

    def check_memory_pressure(self) -> None:
        """Check memory pressure and clear caches if needed."""
        memory_manager.clear_caches_if_needed()


class BalanceCache:
    """Cache for SRC-20 balances."""

    cache: LRUCache[D]

    def __init__(self, max_size: int = 10000) -> None:
        """Initialize the balance cache."""
        self.cache = LRUCache[D](max_size=max_size)

    def get(self, tick: str, tick_hash: str, address: str) -> Optional[D]:
        """Get balance from cache."""
        return self.cache.get(f"{tick}:{tick_hash}:{address}")

    def set(self, tick: str, tick_hash: str, address: str, balance: D) -> None:
        """Set balance in cache."""
        cache_manager.check_memory_pressure()
        self.cache.set(f"{tick}:{tick_hash}:{address}", balance)

    def invalidate(self, tick: str, tick_hash: str, address: str) -> None:
        """Invalidate a specific cache entry."""
        key = f"{tick}:{tick_hash}:{address}"
        if self.cache.contains(key):
            self.cache.invalidate(key)

    def clear(self) -> None:
        """Clear the cache."""
        self.cache.clear()


class TotalMintedCache:
    """Cache for total minted amounts."""

    cache: LRUCache[D]

    def __init__(self, max_size: int = 10000) -> None:
        """Initialize the total minted cache."""
        self.cache = LRUCache[D](max_size=max_size)

    def get(self, tick: str) -> Optional[D]:
        """Get total minted amount from cache."""
        return self.cache.get(tick)

    def set(self, tick: str, amount: D) -> None:
        """Set total minted amount in cache."""
        cache_manager.check_memory_pressure()
        self.cache.set(tick, amount)

    def invalidate(self, tick: str) -> None:
        """Invalidate a specific cache entry."""
        if self.cache.contains(tick):
            self.cache.invalidate(tick)

    def clear(self) -> None:
        """Clear the cache."""
        self.cache.clear()


# Global instances
cache_manager: CacheManager = CacheManager()
balance_cache: BalanceCache = BalanceCache()
total_minted_cache: TotalMintedCache = TotalMintedCache()

# Register caches with the manager
cache_manager.register_cache("balance", balance_cache.cache)
cache_manager.register_cache("total_minted", total_minted_cache.cache)

# Cache for deploy data
deploy_cache = LRUCache[DeployResult](max_size=1000)  # (lim, max, dec)
block_cache = LRUCache[Any](max_size=2)
stamp_cache = LRUCache[int](max_size=2)
reissue_cache = LRUCache[bool](max_size=100000)
subasset_cache = LRUCache[str](max_size=1000)
collection_cache = LRUCache[str](max_size=1000)
price_cache = LRUCache[Optional[Dict[int, Any]]](max_size=1000)  # For SRC-101 price data

# Type alias for SRC-101 deploy data
SRC101DeployResult = Tuple[
    Optional[Any],  # lim
    Optional[Any],  # pri
    Optional[Any],  # mintstart
    Optional[Any],  # mintend
    Optional[List[str]],  # rec
    Optional[Any],  # wla
    Optional[Any],  # imglp
    Optional[Any],  # imgf
    Optional[Any],  # idua
]

# Cache for SRC-101 deploy data
src101_deploy_cache = LRUCache[SRC101DeployResult](max_size=1000)

# Register additional caches
cache_manager.register_cache("deploy", deploy_cache)
cache_manager.register_cache("block", block_cache)
cache_manager.register_cache("stamp", stamp_cache)
cache_manager.register_cache("reissue", reissue_cache)
cache_manager.register_cache("subasset", subasset_cache)
cache_manager.register_cache("collection", collection_cache)
cache_manager.register_cache("price", price_cache)
cache_manager.register_cache("src101_deploy", src101_deploy_cache)


def clear_all_caches() -> None:
    """Global function to clear all caches in the system."""
    cache_manager.clear_all()
