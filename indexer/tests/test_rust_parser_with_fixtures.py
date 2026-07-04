import json
import unittest
from pathlib import Path

import pytest

from btc_stamps_parser import FastTransactionParser


class TestRustParserWithFixtures(unittest.TestCase):
    """Test Rust parser using fixtures instead of requiring a Bitcoin node."""

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

        # Extract test data
        cls.special_transactions = cls.fixtures["special_transactions"]
        cls.test_block_data = cls.fixtures["test_block_700000"]

        # Known includable transactions from fixtures
        cls.test_tx_hashes = [tx["txid"] for tx in cls.special_transactions]
        cls.test_tx_hexes = {tx["txid"]: tx["hex"] for tx in cls.special_transactions}

        # Block data
        cls.test_block_hash = cls.test_block_data["hash"]
        cls.test_block_hex = cls.test_block_data["hex"]

    def setUp(self):
        self.parser = FastTransactionParser()

    def test_single_transaction_parsing(self):
        """Test parsing a single transaction from fixtures"""
        # Use first special transaction
        test_tx_hash = self.test_tx_hashes[0]
        tx_hex = self.test_tx_hexes[test_tx_hash]

        # Parse transaction
        tx_info = self.parser.deserialize_transaction(tx_hex)

        # Verify basic transaction properties
        self.assertEqual(tx_info.txid, test_tx_hash)
        self.assertTrue(len(tx_info.inputs) > 0)  # Should have at least one input
        self.assertTrue(len(tx_info.outputs) > 0)  # Should have at least one output

        # Verify transaction has should_include attribute
        self.assertTrue(hasattr(tx_info, "should_include"), "Transaction should have should_include attribute")

    def test_block_parsing(self):
        """Test parsing an entire block from fixtures"""
        # Parse block
        tx_hash_list, raw_transactions, timestamp, prev_block_hash, bits = self.parser.parse_block(self.test_block_hex)

        # Verify block properties
        self.assertTrue(isinstance(tx_hash_list, list), "tx_hash_list should be a list")
        self.assertTrue(isinstance(raw_transactions, dict), "raw_transactions should be a dict")
        self.assertTrue(isinstance(timestamp, int), "timestamp should be an int")
        self.assertTrue(isinstance(prev_block_hash, str), "prev_block_hash should be a string")

        # Verify against fixture data
        self.assertEqual(timestamp, self.test_block_data["timestamp"])
        self.assertEqual(prev_block_hash, self.test_block_data["prev_hash"])
        self.assertEqual(len(tx_hash_list), self.test_block_data["tx_count"])

    def test_batch_transaction_parsing(self):
        """Test parsing multiple transactions in batch from fixtures"""
        # Get all transaction hexes from fixtures
        tx_hexes = list(self.test_tx_hexes.values())

        # Parse transactions in batch
        tx_infos = self.parser.batch_parse_transactions(tx_hexes)

        # Verify that all returned transactions have should_include=True
        for tx_info in tx_infos:
            self.assertTrue(tx_info.should_include, f"Transaction {tx_info.txid} was returned but has should_include=False")

            # Verify the transaction is in our original list
            self.assertIn(
                tx_info.txid, self.test_tx_hashes, f"Transaction {tx_info.txid} was not in the original list of transactions"
            )

        # Verify that all expected transactions were returned
        returned_txids = {tx_info.txid for tx_info in tx_infos}
        for tx_hash in self.test_tx_hashes:
            self.assertIn(tx_hash, returned_txids, f"Expected transaction {tx_hash} was not returned")

    def test_sample_block_transactions(self):
        """Test parsing sample transactions from the block"""
        # Use sample transactions from the block
        for sample_tx in self.test_block_data["sample_txs"]:
            tx_hex = sample_tx["hex"]
            expected_txid = sample_tx["txid"]

            # Parse transaction
            tx_info = self.parser.deserialize_transaction(tx_hex)

            # Verify txid matches
            self.assertEqual(tx_info.txid, expected_txid)

            # Verify basic structure
            self.assertTrue(hasattr(tx_info, "inputs"))
            self.assertTrue(hasattr(tx_info, "outputs"))
            self.assertTrue(hasattr(tx_info, "should_include"))

    def test_invalid_transaction(self):
        """Test handling of invalid transaction data"""
        invalid_hex = "invalid_hex_data"

        # Should raise an exception for invalid hex
        with self.assertRaises(Exception):
            self.parser.deserialize_transaction(invalid_hex)

    def test_empty_transaction(self):
        """Test handling of empty transaction data"""
        empty_hex = ""

        # Should raise an exception for empty data
        with self.assertRaises(Exception):
            self.parser.deserialize_transaction(empty_hex)


if __name__ == "__main__":
    unittest.main()
