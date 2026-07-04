#!/usr/bin/env python3
"""
Test script to verify the performance improvements from our Rust parser changes.

This script compares the performance of the Rust parser before and after our changes.
"""

import gc
import json
import logging
import os
import sys
import time
from datetime import datetime

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from bitcoin.core import CTransaction

import config
from index_core import util
from index_core.backend import Backend
from index_core.block_validation import filter_block_transactions
from index_core.parser import EnhancedCTransaction, Parser
from index_core.transaction_utils import quick_filter_src20_transaction

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize backend and parser
backend = Backend()
parser = Parser()

# Test parameters
block_index = 795419  # Block with known SRC-20 transactions
target_txid = "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"  # Known SRC-20 transaction

# Set the current block index to ensure proper filtering
# This is critical for the filter_block_transactions function
os.environ["CURRENT_BLOCK_INDEX"] = "784000"  # Set to a block after SRC-20 genesis


def load_test_transactions(json_file):
    """Load test transactions from a JSON file."""
    with open(json_file, "r") as f:
        transactions = json.load(f)
    return transactions


def test_rust_filtering():
    """Test the Rust parser's filtering performance."""
    # Load test transactions
    json_file = os.path.join(os.path.dirname(__file__), "data/test_transactions.json")
    if not os.path.exists(json_file):
        print(f"Test transactions file not found: {json_file}")
        print("Please run create_test_transactions.py first to create test transactions.")
        return

    transactions = load_test_transactions(json_file)
    print(f"Loaded {len(transactions)} test transactions")

    # Extract transaction hexes and IDs
    tx_hexes = [tx["hex"] for tx in transactions]
    tx_ids = [tx["txid"] for tx in transactions]

    # Initialize the Parser to get access to the Rust parser
    parser = Parser()
    rust_parser = parser._parser  # This is the FastParser instance

    # Time the Rust parser's batch processing
    start_time = time.time()
    rust_results = rust_parser.batch_parse_transactions(tx_hexes)
    rust_time = time.time() - start_time

    # Count how many transactions the Rust parser included
    included_count = len(rust_results)

    print(f"\nRust Parser Performance:")
    print(f"Total transactions: {len(transactions)}")
    print(f"Transactions included: {included_count}")
    print(f"Filtering ratio: {included_count / len(transactions) * 100:.2f}%")
    print(f"Processing time: {rust_time:.4f} seconds")

    # Create a mock block structure for filter_block_transactions
    # This should match the structure expected by filter_block_transactions
    mock_block = {"tx": transactions}

    # Time the Python filter_block_transactions function
    start_time = time.time()
    python_results = filter_block_transactions(mock_block)
    python_time = time.time() - start_time

    # Extract the transaction IDs from the Python results
    python_txids = set(python_results[0])  # filter_block_transactions returns a tuple (tx_hash_list, raw_transactions)

    print(f"\nPython Filter Performance:")
    print(f"Total transactions: {len(transactions)}")
    print(f"Transactions included: {len(python_txids)}")
    print(f"Filtering ratio: {len(python_txids) / len(transactions) * 100:.2f}%")
    print(f"Processing time: {python_time:.4f} seconds")

    # Map Rust results to original transaction IDs
    rust_txids = set()
    for i, tx in enumerate(rust_results):
        # Get the txid from the TransactionInfo object
        rust_txids.add(tx.txid)

    # Get the set of stamp transaction IDs from the original transactions
    stamp_txids = {tx["txid"] for tx in transactions if tx["txid"].startswith("stamp_tx_")}

    # Compare the results
    common_txids = rust_txids.intersection(python_txids)
    rust_only = rust_txids - python_txids
    python_only = python_txids - rust_txids

    print(f"\nComparison Results:")
    print(f"Transactions in both: {len(common_txids)}")
    print(f"Transactions only in Rust: {len(rust_only)}")
    print(f"Transactions only in Python: {len(python_only)}")

    # Verify that the Rust parser included all stamp transactions
    rust_stamp_txids = {txid for txid in rust_txids if txid.startswith("stamp_tx_")}
    print(f"\nVerification:")
    print(f"Total stamp transactions: {len(stamp_txids)}")
    print(f"Stamp transactions included by Rust: {len(rust_stamp_txids)}")
    print(f"Stamp transactions included by Python: {len(stamp_txids.intersection(python_txids))}")

    # Performance improvement
    if python_time > 0:
        speedup = python_time / rust_time
        print(f"\nPerformance speedup: {speedup:.2f}x")

    return {
        "rust_count": included_count,
        "python_count": len(python_txids),
        "rust_time": rust_time,
        "python_time": python_time,
        "common_count": len(common_txids),
        "rust_only": len(rust_only),
        "python_only": len(python_only),
    }


if __name__ == "__main__":
    print(f"Running Rust filtering test at {datetime.now()}")
    results = test_rust_filtering()
    print("\nTest completed.")
