#!/usr/bin/env python
"""
Test script to validate the EnhancedCTransaction wrapper and Rust parser integration.

This script tests the EnhancedCTransaction wrapper with specific transactions
mentioned in the documentation to ensure that all critical attributes are preserved
during the conversion from Rust TransactionInfo to Python CTransaction.
"""

import binascii
import logging
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

import config
import index_core.util as util
from index_core.backend import Backend
from index_core.parser import EnhancedCTransaction, Parser


def test_enhanced_ctransaction():
    """Test the EnhancedCTransaction wrapper."""
    logger.info("Testing EnhancedCTransaction wrapper")

    # Initialize backend and parser
    backend = Backend()
    parser = Parser()

    # Test transactions from the documentation
    test_txids = [
        # Transaction 1: Has a multisig output with keyburn and valid SRC-20 data
        "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2",
        # Transaction 2: Has two multisig outputs with keyburn, one with valid SRC-20 data
        "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc",
        # Transaction 3: Has two multisig outputs with keyburn, one with valid SRC-20 data
        "50aeb77245a9483a5b077e4e7506c331dc2f628c22046e7d2b4c6ad6c6236ae1",
    ]

    # Set the current block index to ensure SRC-20 transactions are processed
    util.CURRENT_BLOCK_INDEX = 795419  # Block containing the first test transaction
    logger.info(f"Set CURRENT_BLOCK_INDEX to {util.CURRENT_BLOCK_INDEX}")
    logger.info(f"SRC20 genesis block is {config.BTC_SRC20_GENESIS_BLOCK}")

    # Test individual transaction parsing
    logger.info("Testing individual transaction parsing")
    for txid in test_txids:
        try:
            # Get the transaction hex
            tx_hex = backend.getrawtransaction(txid)
            logger.info(f"Transaction {txid} hex length: {len(tx_hex)}")

            # Parse with Rust parser directly
            rust_parser = parser._parser
            tx_info = rust_parser.deserialize_transaction(tx_hex)
            logger.info(
                f"Rust parser result for {txid}: should_include={tx_info.should_include}, "
                f"has_valid_data={tx_info.has_valid_data}, keyburn={tx_info.keyburn}"
            )

            # Convert to EnhancedCTransaction
            ctx = parser._convert_to_ctransaction(tx_info)

            # Verify that it's an EnhancedCTransaction instance
            if isinstance(ctx, EnhancedCTransaction):
                logger.info(f"Successfully converted to EnhancedCTransaction")
            else:
                logger.error(f"Failed to convert to EnhancedCTransaction, got {type(ctx)}")
                continue

            # Verify that all critical attributes are preserved
            logger.info(
                f"EnhancedCTransaction attributes for {txid}: "
                f"txid={ctx.txid}, "
                f"should_include={ctx.should_include}, "
                f"has_valid_data={ctx.has_valid_data}, "
                f"keyburn={ctx.keyburn}"
            )

            # Verify that the txid matches
            if ctx.txid == txid:
                logger.info(f"✅ txid matches: {txid}")
            else:
                logger.error(f"❌ txid mismatch: expected {txid}, got {ctx.txid}")

            # Verify that should_include matches
            if ctx.should_include == tx_info.should_include:
                logger.info(f"✅ should_include matches: {ctx.should_include}")
            else:
                logger.error(f"❌ should_include mismatch: expected {tx_info.should_include}, got {ctx.should_include}")

            # Verify that has_valid_data matches
            if ctx.has_valid_data == tx_info.has_valid_data:
                logger.info(f"✅ has_valid_data matches: {ctx.has_valid_data}")
            else:
                logger.error(f"❌ has_valid_data mismatch: expected {tx_info.has_valid_data}, got {ctx.has_valid_data}")

            # Verify that keyburn matches
            if ctx.keyburn == tx_info.keyburn:
                logger.info(f"✅ keyburn matches: {ctx.keyburn}")
            else:
                logger.error(f"❌ keyburn mismatch: expected {tx_info.keyburn}, got {ctx.keyburn}")

            # Verify that we can access CTransaction attributes
            try:
                vin_count = len(ctx.vin)
                vout_count = len(ctx.vout)
                version = ctx.nVersion
                logger.info(f"CTransaction attributes: vin_count={vin_count}, vout_count={vout_count}, version={version}")
                logger.info(f"✅ Successfully accessed CTransaction attributes")
            except Exception as e:
                logger.error(f"❌ Failed to access CTransaction attributes: {e}")

            logger.info("-" * 80)
        except Exception as e:
            logger.error(f"Error processing transaction {txid}: {e}")
            logger.info("-" * 80)

    # Test batch transaction parsing
    logger.info("Testing batch transaction parsing")
    try:
        # Get all transaction hexes
        tx_hexes = [backend.getrawtransaction(txid) for txid in test_txids]

        # Parse with batch_parse_transactions
        parsed_txs = parser.batch_parse_transactions(tx_hexes)
        logger.info(f"Batch parsing returned {len(parsed_txs)} transactions")

        # Verify that all transactions are returned
        if len(parsed_txs) == len(test_txids):
            logger.info(f"✅ All {len(test_txids)} transactions were returned")
        else:
            logger.error(f"❌ Expected {len(test_txids)} transactions, got {len(parsed_txs)}")

        # Verify that all transactions are EnhancedCTransaction instances
        all_enhanced = all(isinstance(tx, EnhancedCTransaction) for tx in parsed_txs)
        if all_enhanced:
            logger.info(f"✅ All transactions are EnhancedCTransaction instances")
        else:
            logger.error(f"❌ Not all transactions are EnhancedCTransaction instances")

        # Verify that all transactions have the critical attributes
        for tx in parsed_txs:
            try:
                # Get the txid
                txid = tx.txid

                # Verify that all critical attributes are accessible
                logger.info(
                    f"Transaction {txid}: "
                    f"should_include={tx.should_include}, "
                    f"has_valid_data={tx.has_valid_data}, "
                    f"keyburn={tx.keyburn}"
                )

                # Verify that we can access CTransaction attributes
                vin_count = len(tx.vin)
                vout_count = len(tx.vout)
                version = tx.nVersion
                logger.info(f"CTransaction attributes: vin_count={vin_count}, vout_count={vout_count}, version={version}")
            except Exception as e:
                logger.error(f"Error accessing attributes for transaction: {e}")

        logger.info("-" * 80)
    except Exception as e:
        logger.error(f"Error in batch transaction parsing: {e}")
        logger.info("-" * 80)

    # Test filter_block_transactions function
    logger.info("Testing filter_block_transactions function")
    try:
        # Get a block containing one of the test transactions
        block_index = 795419  # Block containing the first test transaction
        block_hash = backend.getblockhash(block_index)
        block_hex = backend.getblock(block_hash, 0)

        # Parse block
        tx_hash_list, raw_transactions, timestamp, prev_block_hash, bits = parser.parse_block(block_hex)
        logger.info(f"Block has {len(tx_hash_list)} transactions")

        # Create a mock block_data structure
        block_data = {"tx": [{"txid": txid, "hex": raw_transactions[txid]} for txid in tx_hash_list]}

        # Call filter_block_transactions
        from index_core.blocks import filter_block_transactions

        filtered_tx_hash_list, filtered_raw_transactions = filter_block_transactions(block_data)

        # Check if test transaction is in the filtered results
        target_txid = test_txids[0]  # First test transaction
        if target_txid in filtered_raw_transactions:
            logger.info(f"✅ Test transaction {target_txid} found in filtered results")
        else:
            logger.error(f"❌ Test transaction {target_txid} NOT found in filtered results")

        logger.info(f"Filtered {len(filtered_raw_transactions)} of {len(tx_hash_list)} transactions")
    except Exception as e:
        logger.error(f"Error in filter_block_transactions test: {e}")

    logger.info("Test completed")


if __name__ == "__main__":
    test_enhanced_ctransaction()
