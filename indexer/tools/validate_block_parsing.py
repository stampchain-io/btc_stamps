#!/usr/bin/env python3
"""
Tool to validate block parsing functionality between Rust parser and Bitcoin RPC.

This validation tool:
1. Fetches raw block hex using getblock with verbosity=0
2. Parses the block hex using both python-bitcoinlib and Rust parser
3. Compares results with getblock verbosity=2 to verify accuracy
4. Useful for debugging parser issues and validating block parsing
"""

import json
import logging
import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from bitcoin.core import CBlock
from bitcoin.core.serialize import deserialize

from index_core.backend import Backend

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def test_block_hex_parsing(block_height: int):
    """Test fetching and parsing raw block hex."""
    logger.info(f"\nTesting block {block_height}...")

    # Initialize the backend
    backend = Backend()

    # Get the block hash
    block_hash = backend.getblockhash(block_height)
    logger.info(f"Block hash: {block_hash}")

    # Method 1: Get raw block hex (verbosity=0)
    logger.info("Fetching raw block hex (verbosity=0)...")
    block_hex = backend.getblock(block_hash, 0)
    logger.info(f"Block hex size: {len(block_hex)} characters ({len(block_hex) // 2} bytes)")

    # Method 2: Get full block data (verbosity=2)
    logger.info("Fetching full block data (verbosity=2)...")
    block_full = backend.getblock(block_hash, 2)

    # Parse the raw hex using python-bitcoinlib
    logger.info("Parsing raw block hex with python-bitcoinlib...")
    try:
        block_bytes = bytes.fromhex(block_hex)
        parsed_block = deserialize(block_bytes, CBlock())
        logger.info(f"Successfully parsed block with {len(parsed_block.vtx)} transactions")
    except Exception as e:
        logger.error(f"Failed to parse block with python-bitcoinlib: {e}")
        parsed_block = None

    # Test Rust parser if available
    logger.info("Testing Rust parser...")
    if backend._parser is not None:
        try:
            # The Rust parser's parse_block method expects raw hex
            tx_hash_list, raw_transactions, timestamp, prev_block_hash, bits = backend._parser.parse_block(block_hex)
            logger.info(f"Rust parser found {len(tx_hash_list)} transactions")
            logger.info(f"Timestamp: {timestamp}")
            logger.info(f"Previous block hash: {prev_block_hash}")

            # Compare transaction counts
            if len(tx_hash_list) == len(block_full["tx"]):
                logger.info("✓ Transaction count matches between Rust parser and RPC")
            else:
                logger.error(f"✗ Transaction count mismatch: Rust={len(tx_hash_list)}, RPC={len(block_full['tx'])}")

            # Verify first few transaction IDs match
            for i in range(min(5, len(tx_hash_list))):
                if tx_hash_list[i] == block_full["tx"][i]["txid"]:
                    logger.info(f"✓ Transaction {i} ID matches: {tx_hash_list[i]}")
                else:
                    logger.error(f"✗ Transaction {i} ID mismatch!")
                    logger.error(f"  Rust: {tx_hash_list[i]}")
                    logger.error(f"  RPC:  {block_full['tx'][i]['txid']}")

        except Exception as e:
            logger.error(f"Rust parser failed: {e}")
    else:
        logger.warning("Rust parser not available")

    # Compare results
    logger.info("\nComparison Summary:")
    logger.info(f"Block height: {block_height}")
    logger.info(f"Block hash: {block_hash}")
    logger.info(f"Transactions (RPC v2): {len(block_full['tx'])}")
    if parsed_block:
        logger.info(f"Transactions (python-bitcoinlib): {len(parsed_block.vtx)}")
    logger.info(f"Block time: {block_full['time']}")

    return True


def main():
    # Test a few different blocks
    test_blocks = [
        779652,  # SRC-20 genesis block
        780000,  # A block after genesis
        820000,  # A more recent block
    ]

    logger.info("Testing raw block hex fetching and parsing...")
    logger.info("=" * 60)

    for block_height in test_blocks:
        try:
            test_block_hex_parsing(block_height)
        except Exception as e:
            logger.error(f"Failed to test block {block_height}: {e}")

    logger.info("\nTest complete!")


if __name__ == "__main__":
    main()
