#!/usr/bin/env python
"""Test script to validate transaction processing in a block context."""

import binascii
import logging
import sys

import config
import index_core.util as util
from index_core.backend import Backend
from index_core.parser import Parser

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def test_block_transaction():
    """Test how a specific transaction is processed in a block context."""
    # Initialize backend and parser
    backend = Backend()
    parser = Parser()

    # Target transaction and block
    target_txid = "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"
    block_index = 795419

    # Set the current block index to ensure SRC-20 transactions are processed
    # This is critical for the filter_block_transactions function
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

    # Check if target transaction is in the block
    if target_txid in tx_hash_list:
        tx_position = tx_hash_list.index(target_txid)
        logger.info(f"Transaction {target_txid} found in block at position {tx_position}")
    else:
        logger.warning(f"Transaction {target_txid} NOT found in block")
        return

    # Get the transaction hex
    tx_hex = raw_transactions[target_txid]

    # Test individual transaction parsing with Rust
    logger.info(f"Testing individual transaction parsing with Rust")
    rust_parser = parser._parser  # This is the FastParser instance
    tx_info = rust_parser.deserialize_transaction(tx_hex)
    logger.info(
        f"Individual parsing result: should_include={tx_info.should_include}, has_valid_data={tx_info.has_valid_data}, keyburn={tx_info.keyburn}"
    )

    # Test batch transaction parsing with Rust
    logger.info(f"Testing batch transaction parsing with Rust")
    tx_hexes = list(raw_transactions.values())
    parsed_txs = rust_parser.batch_parse_transactions(tx_hexes)
    logger.info(f"Batch parsing returned {len(parsed_txs)} transactions")

    # Check if target transaction is in the parsed results
    target_found = False
    for tx in parsed_txs:
        if tx.txid == target_txid:
            logger.info(
                f"Target transaction found in batch results: should_include={tx.should_include}, has_valid_data={tx.has_valid_data}, keyburn={tx.keyburn}"
            )
            target_found = True

    if not target_found:
        logger.warning(f"Target transaction NOT found in batch results")

    # Test Python parser's batch_parse_transactions
    logger.info(f"Testing Python parser's batch_parse_transactions")
    python_parsed_txs = parser.batch_parse_transactions(tx_hexes)
    logger.info(f"Python batch parsing returned {len(python_parsed_txs)} transactions")

    # Check if target transaction is in the Python parsed results
    target_found = False

    # Get the raw transaction at the known position
    target_tx_hex = tx_hexes[tx_position]
    target_tx_parsed = python_parsed_txs[tx_position]

    # Verify it's the correct transaction by comparing the hash
    tx_hash = target_tx_parsed.GetHash()
    tx_hash_hex = binascii.hexlify(tx_hash[::-1]).decode("utf-8")  # Reverse the bytes before converting to hex

    if tx_hash_hex == target_txid:
        logger.info(f"Target transaction found in Python batch results at position {tx_position}")
        target_found = True
    else:
        logger.warning(f"Transaction at position {tx_position} has hash {tx_hash_hex}, expected {target_txid}")

    if not target_found:
        # Try to find it by scanning all transactions
        logger.info("Scanning all Python parsed transactions to find target")
        for i, tx in enumerate(python_parsed_txs):
            tx_hash = tx.GetHash()
            tx_hash_hex = binascii.hexlify(tx_hash[::-1]).decode("utf-8")

            if tx_hash_hex == target_txid:
                logger.info(f"Target transaction found in Python batch results at position {i}")
                target_found = True
                break

        if not target_found:
            logger.warning(f"Target transaction NOT found in Python batch results after full scan")

    # Check if the transaction is properly parsed by the Python implementation
    ctx = backend.deserialize(tx_hex)
    from index_core.transaction_utils import quick_filter_src20_transaction

    filter_result = quick_filter_src20_transaction(ctx)
    logger.info(f"Python quick filter result for transaction {target_txid}: {filter_result}")

    # Test the filter_block_transactions function
    logger.info("Testing filter_block_transactions function")
    from index_core.block_validation import filter_block_transactions

    # Create a mock block_data structure
    block_data = {"tx": [{"txid": txid, "hex": raw_transactions[txid]} for txid in tx_hash_list]}

    # Call filter_block_transactions
    filtered_tx_hash_list, filtered_raw_transactions = filter_block_transactions(block_data)

    # Check if target transaction is in the filtered results
    if target_txid in filtered_raw_transactions:
        logger.info(f"Target transaction found in filtered results")
    else:
        logger.warning(f"Target transaction NOT found in filtered results")

    # Debug the filter_block_transactions function
    logger.info(f"Filtered {len(filtered_raw_transactions)} of {len(tx_hash_list)} transactions")


if __name__ == "__main__":
    test_block_transaction()
