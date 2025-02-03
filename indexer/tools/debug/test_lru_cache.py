#!/usr/bin/env python3
"""
Test script for the LRU cache implementation in the Rust parser.
"""

import logging
import os
import random
import string
import sys
import time
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("lru_cache_test")

try:
    from btc_stamps_parser import FastTransactionParser

    logger.info("Successfully imported FastTransactionParser")
except ImportError as e:
    logger.error(f"Failed to import FastTransactionParser: {e}")
    logger.error("Make sure to build the Rust parser with 'poetry run maturin develop'")
    sys.exit(1)

# A valid Bitcoin transaction hex (P2PKH)
VALID_TX_HEX = "0100000001c997a5e56e104102fa209c6a852dd90660a20b2d9c352423edce25857fcd3704000000004847304402204e45e16932b8af514961a1d3a1a25fdf3f4f7732e9d624c6c61548ab5fb8cd410220181522ec8eca07de4860a4acdd12909d831cc56cbbac4622082221a8768d1d0901ffffffff0200ca9a3b00000000434104ae1a62fe09c5f51b13905f07f06b99a2f7159b2225f374cd378d71302fa28414e7aab37397f554a7df5f142c21c1b7303b8a0626f1baded5c72a704f7e6cd84cac00286bee0000000043410411db93e1dcdb8a016b49840f8c53bc1eb68a382e97b1482ecad7b148a6909a5cb2e0eaddfb84ccf9744464f82e160bfa9b8b64f9d4c03f999b8643f656b412a3ac00000000"


def generate_modified_tx_hex(base_tx_hex, modification_factor=0.05):
    """Generate a slightly modified transaction hex based on the base transaction."""
    tx_bytes = bytearray.fromhex(base_tx_hex)

    # Modify a small percentage of bytes
    num_bytes_to_modify = max(1, int(len(tx_bytes) * modification_factor))
    for _ in range(num_bytes_to_modify):
        pos = random.randint(0, len(tx_bytes) - 1)
        tx_bytes[pos] = random.randint(0, 255)

    return tx_bytes.hex()


def test_lru_cache():
    """Test the LRU cache implementation in the Rust parser."""
    logger.info("Starting LRU cache test")

    # Create a parser instance
    parser = FastTransactionParser()
    logger.info("Created FastTransactionParser instance")

    # Get initial cache stats
    stats = parser.get_cache_stats()
    logger.info(f"Initial cache stats: {stats}")

    # Generate some transaction hexes based on the valid transaction
    num_txs = 1000
    tx_hexes = [generate_modified_tx_hex(VALID_TX_HEX) for _ in range(num_txs)]
    logger.info(f"Generated {num_txs} transaction hexes")

    # Try to parse the transactions
    start_time = time.time()
    for i, tx_hex in enumerate(tx_hexes):
        try:
            parser.deserialize_transaction(tx_hex)
        except Exception as e:
            logger.debug(f"Failed to parse transaction {i}: {e}")

        if (i + 1) % 100 == 0:
            logger.info(f"Processed {i + 1}/{num_txs} transactions")
            # Check cache stats periodically
            stats = parser.get_cache_stats()
            logger.info(f"Cache stats after {i + 1} transactions: {stats}")

    parse_time = time.time() - start_time
    logger.info(f"Parsing time: {parse_time:.2f} seconds")

    # Get cache stats after parsing
    stats = parser.get_cache_stats()
    logger.info(f"Cache stats after parsing: {stats}")

    # Test cache hits
    logger.info("Testing cache hits...")
    start_time = time.time()
    for i, tx_hex in enumerate(tx_hexes[:100]):  # Use the first 100 transactions
        try:
            parser.deserialize_transaction(tx_hex)
        except Exception:
            pass

        if (i + 1) % 10 == 0:
            logger.info(f"Processed {i + 1}/100 transactions for cache hit test")

    cache_hit_time = time.time() - start_time
    logger.info(f"Cache hit time: {cache_hit_time:.2f} seconds")

    # Generate more transactions to test LRU eviction
    logger.info("Testing LRU eviction...")
    more_txs = 15000  # This should exceed the cache capacity (10000)
    more_tx_hexes = [generate_modified_tx_hex(VALID_TX_HEX) for _ in range(more_txs)]

    start_time = time.time()
    for i, tx_hex in enumerate(more_tx_hexes):
        try:
            parser.deserialize_transaction(tx_hex)
        except Exception:
            pass

        if (i + 1) % 1000 == 0:
            logger.info(f"Processed {i + 1}/{more_txs} transactions for LRU eviction test")
            # Get cache stats during eviction
            stats = parser.get_cache_stats()
            logger.info(f"Cache stats during eviction: {stats}")

    eviction_time = time.time() - start_time
    logger.info(f"LRU eviction time: {eviction_time:.2f} seconds")

    # Final cache stats
    stats = parser.get_cache_stats()
    logger.info(f"Final cache stats: {stats}")

    # Clear the cache
    parser.clear_cache()
    logger.info("Cleared cache")

    # Verify cache is empty
    stats = parser.get_cache_stats()
    logger.info(f"Cache stats after clearing: {stats}")

    return {"parse_time": parse_time, "cache_hit_time": cache_hit_time, "eviction_time": eviction_time, "final_stats": stats}


if __name__ == "__main__":
    logger.info(f"Running LRU cache test at {datetime.now()}")
    results = test_lru_cache()
    logger.info(f"Test completed with results: {results}")
