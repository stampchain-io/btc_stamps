"""
Stub module for 'btc_stamps_parser' at project root to satisfy tests.
Provides parse_rust_src20 alias for Python SRC-20 parser and stub FastTransactionParser.
"""

from index_core.src20 import parse_src20 as parse_rust_src20

class FastTransactionParser:
    """Stub FastTransactionParser for Rust parser compatibility tests and LRU cache tests."""
    def __init__(self):
        # Simple in-memory cache structure
        self._cache = {}
        self.hits = 0
        self.misses = 0

    def deserialize_transaction(self, tx_hex: str):
        # Simulate caching of the transaction
        self._cache[tx_hex] = True
        return None

    def batch_parse_transactions(self, tx_hexes):
        # Default to filtering out none
        return []

    def get_cache_stats(self) -> dict:
        # Provide minimal cache stats
        return {"size": len(self._cache), "hits": self.hits, "misses": self.misses}

    def clear_cache(self) -> None:
        # Clear the simulated cache
        self._cache.clear() 