import unittest

from btc_stamps_parser import FastTransactionParser
from tests.bitcoin_fixtures_loader import BitcoinFixturesLoader


class TestRustParser(unittest.TestCase):
    """Test the Rust parser using fixture data instead of live Bitcoin node"""
    
    @classmethod
    def setUpClass(cls):
        """Load test fixtures once for all tests"""
        cls.fixtures_loader = BitcoinFixturesLoader()
        
        # Get special transactions from fixtures
        special_txs = cls.fixtures_loader.get_special_transactions()
        cls.tx_fixtures = {}
        for tx in special_txs:
            cls.tx_fixtures[tx["txid"]] = tx["hex"]
        
        # Get block data from fixtures if available
        try:
            block_data = cls.fixtures_loader.get_block_data()
            cls.block_fixtures = block_data if block_data else {}
        except:
            cls.block_fixtures = {}
        
    def setUp(self):
        self.parser = FastTransactionParser()
        
        # Use the first transaction from fixtures as test data
        if self.tx_fixtures:
            self.test_tx_hash = list(self.tx_fixtures.keys())[0]
            self.test_tx_hex = list(self.tx_fixtures.values())[0]
        else:
            self.skipTest("No transaction fixtures available")

    def test_single_transaction_parsing(self):
        """Test parsing a single transaction"""
        # Use fixture data
        tx_hex = self.test_tx_hex

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
        # Skip this test as we don't have raw block hex in fixtures
        # Block parsing would require full block hex data which is very large
        self.skipTest("Block parsing test requires raw block hex data not available in fixtures")

    def test_batch_transaction_parsing(self):
        """Test parsing multiple transactions in batch"""
        # Use all available transaction fixtures
        tx_hexes = list(self.tx_fixtures.values())
        tx_hashes = list(self.tx_fixtures.keys())

        # Parse transactions in batch
        tx_infos = self.parser.batch_parse_transactions(tx_hexes)

        # The parser only returns transactions that should be included
        # Verify all returned transactions
        returned_txids = [tx_info.txid for tx_info in tx_infos]
        
        # At least some transactions should be returned
        self.assertGreater(len(tx_infos), 0, "No transactions were included by the parser")
        
        # Verify that all returned transactions have should_include=True
        for tx_info in tx_infos:
            self.assertTrue(tx_info.should_include, f"Transaction {tx_info.txid} was returned but has should_include=False")
            # Verify the transaction is in our original list
            self.assertIn(tx_info.txid, tx_hashes, f"Transaction {tx_info.txid} was not in the original list")

    def test_invalid_transaction(self):
        """Test parsing an invalid transaction"""
        # Test with invalid hex data
        invalid_hex = "invalid_hex_data"
        
        # This should raise an exception or return None
        with self.assertRaises(Exception):
            self.parser.deserialize_transaction(invalid_hex)

    def test_empty_transaction(self):
        """Test parsing an empty transaction"""
        # Test with empty hex
        empty_hex = ""
        
        # This should raise an exception or return None
        with self.assertRaises(Exception):
            self.parser.deserialize_transaction(empty_hex)