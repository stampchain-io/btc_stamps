#!/usr/bin/env python3
"""
Test script to verify the filtering performance of the Rust parser.

This script tests the current implementation of the Rust parser and measures
how many transactions are filtered out vs. how many are passed to Python.
"""

import logging
import os
import sys
import time

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import config
from index_core import backend, parser, util
from index_core.blocks import filter_block_transactions

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test parameters
block_index = 795419  # Block with known SRC-20 transactions
target_txid = "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"  # Known SRC-20 transaction


def test_filtering_performance():
    """Test the filtering performance of the Rust parser."""
    # Set the current block index to ensure SRC-20 transactions are processed
    util.CURRENT_BLOCK_INDEX = block_index
    logger.info(f"Set CURRENT_BLOCK_INDEX to {block_index}")
    logger.info(f"SRC20 genesis block is {config.BTC_SRC20_GENESIS_BLOCK}")

    # Get block data
    logger.info(f"Getting block {block_index}")
    block_hash = backend.getblockhash(block_index)
    block_hex = backend.getblock(block_hash, 0)

    # Parse block
    logger.info(f"Parsing block {block_index}")
    tx_hash_list, raw_transactions, timestamp, prev_block_hash, bits = parser.parse_block(block_hex)
    logger.info(f"Block has {len(tx_hash_list)} transactions")

    # Create a mock block_data structure
    block_data = {"tx": [{"txid": txid, "hex": raw_transactions[txid]} for txid in tx_hash_list]}

    # Test before optimization
    start_time = time.time()
    filtered_tx_hash_list, filtered_raw_transactions = filter_block_transactions(block_data)
    end_time = time.time()

    logger.info(f"Before optimization:")
    logger.info(f"  Total transactions: {len(tx_hash_list)}")
    logger.info(f"  Filtered transactions: {len(filtered_tx_hash_list)}")
    logger.info(f"  Processing time: {end_time - start_time:.4f} seconds")

    # Check if target transaction is in the filtered results
    if target_txid in filtered_raw_transactions:
        logger.info(f"Target transaction found in filtered results")
    else:
        logger.warning(f"Target transaction NOT found in filtered results")

    # Additional verification
    # Count how many transactions the Rust parser thinks should be included
    rust_parser = parser._parser  # This is the FastParser instance
    tx_hexes = list(raw_transactions.values())

    start_time = time.time()
    parsed_txs = rust_parser.batch_parse_transactions(tx_hexes)
    end_time = time.time()

    should_include_count = sum(1 for tx in parsed_txs if tx.should_include)

    logger.info(f"Rust parser analysis:")
    logger.info(f"  Total transactions processed: {len(tx_hexes)}")
    logger.info(f"  Transactions that should be included: {should_include_count}")
    logger.info(f"  Processing time: {end_time - start_time:.4f} seconds")

    # Verify that the number of transactions that should be included matches the number of filtered transactions
    if should_include_count == len(filtered_raw_transactions):
        logger.info(
            "Verification successful: Rust parser and filter_block_transactions agree on the number of transactions to include"
        )
    else:
        logger.warning(
            f"Verification failed: Rust parser says {should_include_count} transactions should be included, but filter_block_transactions returned {len(filtered_raw_transactions)}"
        )


if __name__ == "__main__":
    test_filtering_performance()
