import logging
import os
import sys
from unittest import TestCase, main

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import index_core.backend as backend
from index_core.transaction_utils import quick_filter_src20_transaction

# Configure logging
logging.basicConfig(level=logging.DEBUG if os.environ.get("RUST_LOG") == "debug" else logging.INFO)
logger = logging.getLogger(__name__)


class TestSpecialTransactions(TestCase):
    """
    Test that special transactions are correctly identified by both Python and Rust implementations.

    These test cases verify that both implementations correctly identify transactions that should be included
    in the indexing process. The transactions used in these tests represent important edge cases that help
    ensure compatibility and correctness between the Python and Rust implementations.

    For detailed information about these test transactions, see the documentation in:
    indexer/docs/rust-python-parser-issues.md
    """

    def setUp(self):
        """Set up the test environment."""
        self.backend = backend.Backend()

        # Special transaction IDs that should be included
        # These transactions are documented in indexer/docs/rust-python-parser-issues.md
        # and represent important test cases for the transaction inclusion logic
        self.special_txids = [
            # Transaction 1: Has a multisig output with keyburn and valid SRC-20 data
            "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2",
            # Transaction 2: Has two multisig outputs with keyburn, one with valid SRC-20 data
            "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc",
        ]

        # Fetch the raw transactions
        self.raw_transactions = {}
        for txid in self.special_txids:
            try:
                tx_hex = self.backend.getrawtransaction(txid)
                self.raw_transactions[txid] = tx_hex
                logger.info(f"Successfully fetched transaction {txid}")
            except Exception as e:
                logger.error(f"Failed to fetch transaction {txid}: {e}")
                raise

    def test_python_implementation(self):
        """
        Test that the Python implementation correctly identifies the special transactions.

        This test verifies that the Python implementation's quick_filter_src20_transaction function
        correctly identifies transactions that should be included in the indexing process.
        """
        for txid, tx_hex in self.raw_transactions.items():
            # Deserialize the transaction
            ctx = self.backend.deserialize(tx_hex)

            # Check if the transaction should be included
            should_include = quick_filter_src20_transaction(ctx)

            logger.info(f"Python implementation: Transaction {txid} should_include = {should_include}")
            self.assertTrue(should_include, f"Python implementation failed to include transaction {txid}")

    def test_rust_implementation(self):
        """
        Test that the Rust implementation correctly identifies the special transactions.

        This test verifies that the Rust implementation's deserialize_transaction function
        correctly identifies transactions that should be included in the indexing process.

        Note: This test accesses the Rust parser directly to get the should_include attribute,
        bypassing the conversion to CTransaction which would lose this attribute.
        """
        if not hasattr(self.backend, "_parser") or self.backend._parser is None:
            self.skipTest("Rust parser not available")

        # Access the Rust parser directly
        rust_parser = self.backend._parser._parser

        for txid, tx_hex in self.raw_transactions.items():
            # Parse the transaction with the Rust parser directly
            tx_info = rust_parser.deserialize_transaction(tx_hex)

            logger.info(f"Rust implementation: Transaction {txid} should_include = {tx_info.should_include}")
            self.assertTrue(tx_info.should_include, f"Rust implementation failed to include transaction {txid}")

    def test_batch_processing(self):
        """
        Test that the Rust batch processing correctly identifies the special transactions.

        This test verifies that the Rust implementation's batch_parse_transactions function
        correctly identifies transactions that should be included in the indexing process
        when processing multiple transactions in a batch.

        Note: The Rust parser now only returns transactions that should be included,
        so we expect all returned transactions to have should_include=True.
        """
        if not hasattr(self.backend, "_parser") or self.backend._parser is None:
            self.skipTest("Rust parser not available")

        # Access the Rust parser directly
        rust_parser = self.backend._parser._parser

        # Create a list of transaction hexes
        tx_hexes = list(self.raw_transactions.values())

        # Process the transactions in batch
        parsed_txs = rust_parser.batch_parse_transactions(tx_hexes)

        # Check that all special transactions were included
        # The Rust parser now only returns transactions that should be included
        self.assertEqual(
            len(parsed_txs),
            len(self.special_txids),
            f"Expected {len(self.special_txids)} transactions to be included, got {len(parsed_txs)}",
        )

        # Verify that all returned transactions have should_include=True
        for tx_info in parsed_txs:
            self.assertTrue(tx_info.should_include, f"Transaction {tx_info.txid} was returned but has should_include=False")

        # Verify that all special transactions are in the returned set
        returned_txids = {tx_info.txid for tx_info in parsed_txs}
        for txid in self.special_txids:
            self.assertIn(txid, returned_txids, f"Special transaction {txid} was not included in the results")


if __name__ == "__main__":
    main()
