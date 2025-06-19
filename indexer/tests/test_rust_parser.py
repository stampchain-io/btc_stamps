import unittest

import pytest

from btc_stamps_parser import FastTransactionParser
from index_core.backend import Backend


@pytest.mark.requires_bitcoin_node
class TestRustParser(unittest.TestCase):
    def setUp(self):
        self.parser = FastTransactionParser()
        try:
            # Create backend with shorter timeout for test environment
            self.backend = Backend()
            # Override the timeout for tests to fail faster
            if hasattr(self.backend._session, "request"):
                import functools

                self.backend._session.request = functools.partial(
                    self.backend._session.request.__wrapped__, timeout=(2, 5)  # 2 second connect, 5 second read timeout
                )
            # Test if we can actually connect to the Bitcoin node
            self.backend.rpc("getblockcount", [])
        except Exception as e:
            self.skipTest(f"Bitcoin node not available: {e}")

        # Using a more recent transaction that we know should be included
        self.test_tx_hash = "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"  # Known includable transaction
        self.test_block_hash = "00000000000000000007878ec04bb2b2e12317804810f4c26033585b3f81ffaa"  # Block 700,000

    def test_single_transaction_parsing(self):
        """Test parsing a single transaction"""
        # Get raw transaction
        tx_hex = self.backend.getrawtransaction(self.test_tx_hash)

        # Parse transaction
        tx_info = self.parser.deserialize_transaction(tx_hex)

        # Verify basic transaction properties
        self.assertEqual(tx_info.txid, self.test_tx_hash)
        self.assertTrue(len(tx_info.inputs) > 0)  # Should have at least one input
        self.assertTrue(len(tx_info.outputs) > 0)  # Should have at least one output

        # Verify transaction has should_include attribute
        self.assertTrue(hasattr(tx_info, "should_include"), "Transaction should have should_include attribute")

    def test_block_parsing(self):
        """Test parsing an entire block"""
        # Get raw block
        block_data = self.backend.rpc("getblock", [self.test_block_hash, 0])

        # Parse block
        tx_hash_list, raw_transactions, timestamp, prev_block_hash, bits = self.parser.parse_block(block_data)

        # Verify block properties
        self.assertTrue(isinstance(tx_hash_list, list), "tx_hash_list should be a list")
        self.assertTrue(isinstance(raw_transactions, dict), "raw_transactions should be a dict")
        self.assertTrue(isinstance(timestamp, int), "timestamp should be an int")
        self.assertTrue(isinstance(prev_block_hash, str), "prev_block_hash should be a string")

    def test_batch_transaction_parsing(self):
        """
        Test parsing multiple transactions in batch.

        Note: The Rust parser now only returns transactions that should be included,
        so we can't assert the exact number of results. We'll use known includable
        transactions for this test.
        """
        # Use known includable transactions
        tx_hashes = [
            "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2",
            "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc",
        ]

        # Get raw transactions
        tx_hexes = [self.backend.getrawtransaction(tx_hash) for tx_hash in tx_hashes]

        # Parse transactions in batch
        tx_infos = self.parser.batch_parse_transactions(tx_hexes)

        # Verify that all returned transactions have should_include=True
        for tx_info in tx_infos:
            self.assertTrue(tx_info.should_include, f"Transaction {tx_info.txid} was returned but has should_include=False")

            # Verify the transaction is in our original list
            self.assertIn(tx_info.txid, tx_hashes, f"Transaction {tx_info.txid} was not in the original list of transactions")

        # Verify that all expected transactions were returned
        returned_txids = {tx_info.txid for tx_info in tx_infos}
        for tx_hash in tx_hashes:
            self.assertIn(tx_hash, returned_txids, f"Expected transaction {tx_hash} was not returned")

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
