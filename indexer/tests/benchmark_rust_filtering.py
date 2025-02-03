#!/usr/bin/env python3
"""
Benchmark script to demonstrate the performance benefits of the Rust parser's transaction filtering.

This script compares the performance of processing all transactions vs. only processing
transactions that should be included.
"""

import gc
import json
import logging
import os
import sys
import time

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import config
from index_core import util
from index_core.backend import Backend
from index_core.blocks import filter_block_transactions, quick_filter_src20_transaction
from index_core.parser import Parser

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize backend and parser
backend = Backend()
parser = Parser()

# Test parameters
block_indices = [795419, 795420, 795421, 795422, 795423]  # Multiple blocks for better benchmarking
target_txid = "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"  # Known SRC-20 transaction


def benchmark_filtering():
    """Benchmark the performance of the Rust parser's transaction filtering."""
    results = {
        "blocks": {},
        "summary": {
            "total_transactions": 0,
            "included_transactions": 0,
            "inclusion_percentage": 0,
            "rust_filtering_time": 0,
            "python_filtering_time": 0,
            "speedup_factor": 0,
        },
    }

    total_transactions = 0
    total_included = 0
    total_rust_time = 0
    total_python_time = 0

    for block_index in block_indices:
        # Set the current block index to ensure SRC-20 transactions are processed
        util.CURRENT_BLOCK_INDEX = block_index
        logger.info(f"Processing block {block_index}")

        # Get block data
        block_hash = backend.getblockhash(block_index)
        block_hex = backend.getblock(block_hash, 0)

        # Parse block
        tx_hash_list, raw_transactions, timestamp, prev_block_hash, bits = parser.parse_block(block_hex)
        logger.info(f"Block has {len(tx_hash_list)} transactions")

        # Create a mock block_data structure
        block_data = {"tx": [{"txid": txid, "hex": raw_transactions[txid]} for txid in tx_hash_list]}

        # Force garbage collection before testing
        gc.collect()

        # Test filter_block_transactions performance (using Rust filtering)
        start_time = time.time()
        filtered_tx_hash_list, filtered_raw_transactions = filter_block_transactions(block_data)
        rust_time = time.time() - start_time

        logger.info(f"Rust filtering performance:")
        logger.info(f"  Total transactions: {len(tx_hash_list)}")
        logger.info(f"  Filtered transactions: {len(filtered_raw_transactions)}")
        logger.info(f"  Processing time: {rust_time:.4f} seconds")

        # Force garbage collection before testing
        gc.collect()

        # Test Python-only filtering performance
        start_time = time.time()
        python_filtered = {}
        for tx in block_data["tx"]:
            try:
                ctx = backend.deserialize(tx["hex"])
                filter_result = quick_filter_src20_transaction(ctx)
                if filter_result:
                    python_filtered[tx["txid"]] = tx["hex"]
            except Exception as e:
                logger.error(f"Error processing transaction {tx['txid']}: {e}")
        python_time = time.time() - start_time

        logger.info(f"Python-only filtering performance:")
        logger.info(f"  Total transactions: {len(tx_hash_list)}")
        logger.info(f"  Filtered transactions: {len(python_filtered)}")
        logger.info(f"  Processing time: {python_time:.4f} seconds")

        # Calculate speedup
        speedup = python_time / rust_time if rust_time > 0 else 0
        logger.info(f"Speedup factor: {speedup:.2f}x")

        # Store results
        results["blocks"][block_index] = {
            "total_transactions": len(tx_hash_list),
            "included_transactions": len(filtered_raw_transactions),
            "inclusion_percentage": len(filtered_raw_transactions) / len(tx_hash_list) * 100 if len(tx_hash_list) > 0 else 0,
            "rust_filtering_time": rust_time,
            "python_filtering_time": python_time,
            "speedup_factor": speedup,
        }

        # Update totals
        total_transactions += len(tx_hash_list)
        total_included += len(filtered_raw_transactions)
        total_rust_time += rust_time
        total_python_time += python_time

    # Calculate summary
    results["summary"]["total_transactions"] = total_transactions
    results["summary"]["included_transactions"] = total_included
    results["summary"]["inclusion_percentage"] = total_included / total_transactions * 100 if total_transactions > 0 else 0
    results["summary"]["rust_filtering_time"] = total_rust_time
    results["summary"]["python_filtering_time"] = total_python_time
    results["summary"]["speedup_factor"] = total_python_time / total_rust_time if total_rust_time > 0 else 0

    # Print summary
    logger.info("\nBenchmark Summary:")
    logger.info(f"Total transactions processed: {total_transactions}")
    logger.info(f"Total transactions included: {total_included} ({results['summary']['inclusion_percentage']:.2f}%)")
    logger.info(f"Total Rust filtering time: {total_rust_time:.4f} seconds")
    logger.info(f"Total Python filtering time: {total_python_time:.4f} seconds")
    logger.info(f"Overall speedup factor: {results['summary']['speedup_factor']:.2f}x")

    # Save results to file
    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)

    logger.info("Benchmark results saved to benchmark_results.json")


if __name__ == "__main__":
    benchmark_filtering()
