#!/usr/bin/env python
import logging
import sys

from src.index_core.blocks import get_transaction_hex
from src.rust_parser.btc_stamps_parser import FastTransactionParser

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def analyze_transaction(tx_id):
    """Analyze a specific transaction using the Rust parser."""
    logger.info(f"Analyzing transaction: {tx_id}")

    # Initialize the Rust parser
    parser = FastTransactionParser()

    # Get the transaction hex
    tx_hex = get_transaction_hex(tx_id)
    if not tx_hex:
        logger.error(f"Could not retrieve transaction hex for {tx_id}")
        return

    logger.info(f"Transaction hex length: {len(tx_hex)}")

    # Parse the transaction using the Rust parser
    tx_info = parser.deserialize_transaction(tx_hex)

    # Print the transaction details
    logger.info(f"Transaction {tx_id} details:")
    logger.info(f"  has_valid_pattern: {tx_info.has_valid_pattern}")
    logger.info(f"  has_valid_data: {tx_info.has_valid_data}")
    logger.info(f"  keyburn: {tx_info.keyburn}")
    logger.info(f"  should_include: {tx_info.should_include}")
    logger.info(f"  outputs: {len(tx_info.outputs)}")

    # Print details for each output
    for i, output in enumerate(tx_info.outputs):
        logger.info(f"  Output {i}:")
        logger.info(f"    has_op_checkmultisig: {output.has_op_checkmultisig}")
        logger.info(f"    keyburn: {output.keyburn}")
        logger.info(f"    last_pubkey: {output.last_pubkey[:30]}...")
        logger.info(f"    script_hex: {output.script_hex[:30]}...")


def main():
    # Transaction IDs to analyze
    tx_ids = [
        "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2",
        "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc",
    ]

    for tx_id in tx_ids:
        analyze_transaction(tx_id)
        print("\n" + "-" * 80 + "\n")


if __name__ == "__main__":
    main()
