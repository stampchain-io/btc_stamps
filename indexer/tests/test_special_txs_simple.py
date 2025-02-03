#!/usr/bin/env python
"""
Test script to verify special transaction handling in the Rust parser.
"""

import logging

from btc_stamps_parser import FastTransactionParser

from index_core.backend import Backend

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    # Initialize backend and parser
    backend = Backend()
    parser = FastTransactionParser()

    # Special transaction IDs that should be included
    txids = [
        "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2",
        "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc",
    ]

    # Test each transaction
    for txid in txids:
        logger.info(f"Testing transaction {txid}")

        # Get transaction hex
        tx_hex = backend.getrawtransaction(txid)

        # Parse with Rust parser
        tx_info = parser.deserialize_transaction(tx_hex)

        # Check if it's included
        logger.info(f"Transaction {txid}: should_include = {tx_info.should_include}")

        # Verify that should_include is True
        assert tx_info.should_include, f"Transaction {txid} should be included but isn't"

    logger.info("All tests passed! Special transactions are correctly included.")


if __name__ == "__main__":
    main()
