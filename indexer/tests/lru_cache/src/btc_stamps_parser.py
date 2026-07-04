"""
Stub module for LRU cache tests under tests/lru_cache/src.
Provides FastTransactionParser with minimal API required by test_lru_cache.
"""


class FastTransactionParser:
    """Minimal stub for LRU cache testing."""

    def __init__(self):
        # Initialize simple cache storage
        self._cache = {}
        self.hits = 0
        self.misses = 0

    def deserialize_transaction(self, tx_hex: str):
        # Simulate caching of tx_hex
        self._cache[tx_hex] = True
        return None

    def get_cache_stats(self) -> dict:
        # Return dict representing cache statistics
        return {"size": len(self._cache), "hits": self.hits, "misses": self.misses}

    def clear_cache(self) -> None:
        # Clear simulated cache
        self._cache.clear()
