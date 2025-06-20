import json
import logging
import os
import sys
from pathlib import Path
from unittest import TestCase, main

import pytest

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import index_core.backend as backend
from index_core.transaction_utils import quick_filter_src20_transaction

# Configure logging
logging.basicConfig(level=logging.DEBUG if os.environ.get("RUST_LOG") == "debug" else logging.INFO)
logger = logging.getLogger(__name__)


class TestSpecialTransactionsWithFixtures(TestCase):
    """
    Test that special transactions are correctly identified by both Python and Rust implementations.
    
    This version uses fixtures instead of requiring a Bitcoin node, making it suitable for CI/CD.
    """

    @classmethod
    def setUpClass(cls):
        """Load fixtures once for all tests."""
        fixtures_path = Path(__file__).parent / "fixtures" / "bitcoin_node_fixtures.json"
        if not fixtures_path.exists():
            raise FileNotFoundError(
                f"Fixtures file not found at {fixtures_path}. "
                "Run 'poetry run python tools/debug/fetch_special_test_fixtures.py' to generate it."
            )
        
        with open(fixtures_path) as f:
            cls.fixtures = json.load(f)
        
        # Extract special transactions
        cls.raw_transactions = {}
        for tx_data in cls.fixtures["special_transactions"]:
            cls.raw_transactions[tx_data["txid"]] = tx_data["hex"]
            logger.info(f"Loaded fixture for transaction {tx_data['txid']}")

    def setUp(self):
        """Set up the test environment."""
        # Create backend without requiring actual Bitcoin node
        self.backend = backend.Backend()
        
        # These are the special transaction IDs from the fixtures
        self.special_txids = list(self.raw_transactions.keys())

    def test_python_implementation(self):
        """
        Test that the Python implementation correctly identifies the special transactions.
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