import json
import os
import sys
import tempfile
import unittest

# Add the parent directory to sys.path to allow relative imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.bitcoin_fixtures_loader import BitcoinFixturesLoader
from tests.mock_transaction import process_transactions
from tests.test_helpers import create_mock_tx_lookup, mock_backend, setup_test_environment


class TestTransactions(unittest.TestCase):
    """Test transaction processing using shared Bitcoin fixtures."""

    @classmethod
    def setUpClass(cls):
        # Set up the test environment
        setup_test_environment()

        # Load Bitcoin fixtures
        cls.fixtures_loader = BitcoinFixturesLoader()

        # Get special transactions from fixtures
        special_txs = cls.fixtures_loader.get_special_transactions()

        # Create transaction data dict from fixtures (first 2 transactions)
        cls.tx_data = {}
        if len(special_txs) >= 2:
            for tx in special_txs[:2]:
                cls.tx_data[tx["txid"]] = tx["hex"]
        else:
            # Fallback to the stamp transactions from analyze_missing_txs.py
            # These are actual SRC-20 stamp transactions from blocks 795419 and 795421
            cls.tx_data = {
                "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2": (
                    special_txs[0]["hex"] if special_txs else ""
                ),
                "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc": (
                    special_txs[1]["hex"] if special_txs else ""
                ),
            }

    def setUp(self):
        """Set up each test method with fresh environment."""
        # Reset test environment for each test to avoid state pollution
        setup_test_environment()

    def tearDown(self):
        """Clean up after each test method."""
        # Additional cleanup if needed
        pass

    def test_process_transactions(self):
        # Debug: ensure we have tx_data
        self.assertIsNotNone(self.tx_data, "tx_data should not be None")
        self.assertGreater(len(self.tx_data), 0, f"tx_data should have items, got: {self.tx_data}")

        # Create a temporary file to store the results
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            output_file = temp_file.name

        try:
            # Create a list of transaction hashes to process
            tx_hashes = list(self.tx_data.keys())
            self.assertEqual(len(tx_hashes), 2, f"Expected 2 tx hashes, got {len(tx_hashes)}: {tx_hashes}")

            # Use the mock_backend context manager to patch the Backend.getrawtransaction method
            with mock_backend() as mock_getrawtx:
                # Set up the mock to use our create_mock_tx_lookup function
                mock_getrawtx.side_effect = create_mock_tx_lookup(self.tx_data)

                # Call the function under test
                result = process_transactions(tx_hashes, output_file=output_file)

                # Verify the results
                self.assertEqual(
                    len(result),
                    len(tx_hashes),
                    f"Expected {len(tx_hashes)} results, got {len(result)}. Mock call count: {mock_getrawtx.call_count}",
                )

                # Verify output file was written correctly
                with open(output_file, "r") as f:
                    saved_data = json.load(f)
                    self.assertEqual(len(saved_data), len(tx_hashes))

                # Make assertions about the mock calls
                self.assertEqual(mock_getrawtx.call_count, len(tx_hashes))

        finally:
            # Clean up the temporary file
            if os.path.exists(output_file):
                os.unlink(output_file)


if __name__ == "__main__":
    unittest.main()
