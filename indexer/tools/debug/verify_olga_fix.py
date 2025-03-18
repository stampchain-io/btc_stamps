"""
Verification script to test that both multisig and P2WSH transactions 
are correctly processed after the BTC_SRC20_OLGA_BLOCK cutoff.

This script processes transactions from block 865003 and verifies they are
correctly handled by the transaction processing pipeline.
"""

import logging
import os
import sys
from datetime import datetime

# Add the indexer directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import project modules
from dotenv import load_dotenv

from src.config import BTC_SRC20_OLGA_BLOCK
from src.index_core import arc4, backend, blocks, script, util


def main():
    """Main function to verify the fix for the multisig processing issue."""
    # Load environment variables
    logger.info("Loading environment variables from .env")
    load_dotenv()

    # Block 865003 is after the OLGA cutoff
    block_index = 865003
    logger.info(f"Testing transactions from block {block_index} (OLGA block: {BTC_SRC20_OLGA_BLOCK})")

    # Set the current block index for the test
    util.CURRENT_BLOCK_INDEX = block_index

    # Create a backend instance
    bitcoin_backend = backend.Backend()

    # Known transaction hashes from block 865003
    tx_hashes = [
        "c8c3831f6354831f1f14ee8f979c2b114d883c85653aae1c2d286ad351dfc30c",
        "8a68d7a9cf316014bc9f9a61583eced0dbf90db08e542639921ce235cd55f82e",
        "943200a9525381c5f128f1b889d0dd0c6a648f131b104b5db095fa82b5dd3304",
        "711ef8be4c0076b267e96afffd71907fd9388ea08e6d93564008e91a040e8d0c",
        "5e7d66b0b1d3bc28d8ed9211262592d44b601f148686a93cc372fc7e5a3bab71",
        "71aa8481fd179b56cbc125a95dad1c24e3146895f3d2dbe60875f549c1359fe7",
        "e70cfa82f5979405e715420af5533bfb8f8a99ec66177b4d6fc1ea790875c99c",
        "1e20a653c0824c10ed9401953927bef16cfaf43411f7d45165b88e252d8a9f48",
        "b7fc8ca93c23d2b0ef4c210147ec56df426139f85c6496db575ffe3c41beedea",
        "0fea78019487990814cfaba4c9b3fd861f70b3190886a659eaedc0bdc221d0ed",
        "3368bd06d79cc3a66a01d55cf81112e92affcb64022d7f1c78fafcad824ea426",
        "8730c7f8940706be7de6c28466b348703c8ddd48bf9a409a483265b7ded07d8e",  # This is a P2WSH transaction
    ]

    success_count = 0
    failure_count = 0

    # Test each transaction
    for tx_hash in tx_hashes:
        logger.info(f"\n===== Testing transaction {tx_hash} =====")

        # Get the transaction hex
        tx_hex = bitcoin_backend.getrawtransaction(tx_hash)

        # Test the quick filter function
        tx = bitcoin_backend.deserialize(tx_hex)
        should_include = blocks.quick_filter_src20_transaction(tx)
        logger.info(f"Quick filter result: should_include={should_include}")

        if not should_include:
            logger.error(f"Transaction {tx_hash} failed the quick filter test")
            failure_count += 1
            continue

        # Test the process_tx function
        result = blocks.process_tx(None, tx_hash, block_index, None, {tx_hash: tx_hex})

        if result and result.data:
            logger.info(f"process_tx returned data: {result.data}")
            logger.info(f"source: {result.source}")
            logger.info(f"destination: {result.destination}")
            logger.info(f"keyburn: {result.keyburn}")
            logger.info(f"TEST PASSED ✓")
            success_count += 1
        else:
            logger.error(f"Transaction {tx_hash} failed process_tx test")
            if result:
                logger.error(f"process_tx returned empty data")
                logger.error(f"source: {result.source}")
                logger.error(f"destination: {result.destination}")
                logger.error(f"keyburn: {result.keyburn}")
            else:
                logger.error("process_tx returned None")
            failure_count += 1

    # Summary
    logger.info("\n===== SUMMARY =====")
    logger.info(f"Tested {len(tx_hashes)} transactions")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {failure_count}")

    if failure_count == 0:
        logger.info("All tests passed! The fix is working correctly.")
    else:
        logger.warning(f"{failure_count} tests failed. The fix may not be complete.")


if __name__ == "__main__":
    main()
