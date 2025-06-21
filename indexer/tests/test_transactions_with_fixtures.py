import json
import os
import tempfile
import unittest

from tests.bitcoin_fixtures_loader import BitcoinFixturesLoader
from tests.mock_transaction import process_transactions
from tests.test_helpers import create_mock_tx_lookup, mock_backend, setup_test_environment


class TestTransactionsWithFixtures(unittest.TestCase):
    """Test transactions using shared Bitcoin fixtures."""

    @classmethod
    def setUpClass(cls):
        # Set up the test environment
        setup_test_environment()

        # Load shared Bitcoin fixtures
        cls.fixtures_loader = BitcoinFixturesLoader()

        # Get special transactions from fixtures
        special_txs = cls.fixtures_loader.get_special_transactions()

        # Create transaction data dict from fixtures (first 2 transactions)
        cls.tx_data = {}
        for tx in special_txs[:2]:
            cls.tx_data[tx["txid"]] = tx["hex"]

    def test_process_transactions_with_fixtures(self):
        """Test processing transactions using shared Bitcoin fixtures."""
        # Create a temporary file to store the results
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            output_file = temp_file.name

        try:
            # Create a list of transaction hashes to process
            tx_hashes = list(self.tx_data.keys())

            # Use the mock_backend context manager to patch the Backend.getrawtransaction method
            with mock_backend() as mock_getrawtx:
                # Set up the mock to use our create_mock_tx_lookup function with fixtures data
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

    def test_process_special_transactions(self):
        """Test processing special edge case transactions from fixtures."""
        # Get stamp-related transactions from fixtures
        stamp_txs = {}
        for tx in self.fixtures_loader.get_special_transactions():
            if "stamp" in tx.get("description", "").lower():
                stamp_txs[tx["txid"]] = tx["hex"]

        if not stamp_txs:
            self.skipTest("No stamp transactions found in fixtures")

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            output_file = temp_file.name

        try:
            tx_hashes = list(stamp_txs.keys())

            with mock_backend() as mock_getrawtx:
                mock_getrawtx.side_effect = create_mock_tx_lookup(stamp_txs)

                result = process_transactions(tx_hashes, output_file=output_file)

                # Basic validation
                self.assertGreater(len(result), 0)
                self.assertEqual(mock_getrawtx.call_count, len(tx_hashes))

        finally:
            if os.path.exists(output_file):
                os.unlink(output_file)


if __name__ == "__main__":
    unittest.main()
