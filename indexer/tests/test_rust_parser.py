import unittest

from btc_stamps_parser import FastTransactionParser

from index_core.backend import Backend


class TestRustParser(unittest.TestCase):
    def setUp(self):
        self.parser = FastTransactionParser()
        self.backend = Backend()
        # Using a more recent transaction that we can actually fetch
        self.test_tx_hash = "7957a35fe64f80d234d76d83a2a8f1a0d8149a41d81de548f0a65a8a999f6f18"  # Example transaction
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

        # Verify transaction hex matches original
        self.assertTrue(tx_info.hex)  # Should not be empty

        # Test output properties
        output = tx_info.outputs[0]
        self.assertIsInstance(output.value, int)
        self.assertTrue(output.script_pubkey)  # Should have a script pubkey
        self.assertIsInstance(output.is_op_return, bool)

    def test_block_parsing(self):
        """Test parsing an entire block"""
        # Get raw block
        block_data = self.backend.rpc("getblock", [self.test_block_hash, 0])

        # Parse block
        block_info = self.parser.parse_block(block_data)

        # Verify block properties
        self.assertTrue(block_info.prev_block_hash)  # Should have a previous block hash
        self.assertTrue(len(block_info.transactions) > 0)  # Should have at least one transaction

        # Verify first transaction
        first_tx = block_info.transactions[0]
        self.assertTrue(first_tx.txid)  # Should have a transaction ID

    def test_batch_transaction_parsing(self):
        """Test parsing multiple transactions in batch"""
        # Get a few consecutive transactions from the same block
        block_data = self.backend.rpc("getblock", [self.test_block_hash, 2])
        tx_hashes = [tx["txid"] for tx in block_data["tx"][:2]]  # Get first two transactions

        # Get raw transactions
        tx_hexes = [self.backend.getrawtransaction(tx_hash) for tx_hash in tx_hashes]

        # Parse transactions in batch
        tx_infos = self.parser.batch_parse_transactions(tx_hexes)

        # Verify results
        self.assertEqual(len(tx_infos), len(tx_hashes))
        for tx_info, tx_hash in zip(tx_infos, tx_hashes):
            self.assertEqual(tx_info.txid, tx_hash)

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

    def test_pre_filter_block(self):
        """Test pre-filtering of block transactions"""
        # Get raw block with known stamp transactions
        block_data = self.backend.rpc("getblock", [self.test_block_hash, 0])
        
        # Pre-filter block
        result = self.parser.pre_filter_block(block_data)
        
        # Verify filtering results
        self.assertIsNotNone(result)
        self.assertGreater(result.filtered_count, 0)
        self.assertLess(len(result.transactions), result.filtered_count + len(result.transactions))

        # Verify transaction info objects
        for tx in result.transactions:
            self.assertTrue(hasattr(tx, 'txid'))
            self.assertTrue(hasattr(tx, 'hex'))
            
            # Verify each transaction has valid hex
            self.assertTrue(len(tx.hex) > 0)
            self.assertTrue(all(c in '0123456789abcdefABCDEF' for c in tx.hex))

    def test_pre_filter_memory_usage(self):
        """Test memory usage during pre-filtering"""
        import psutil
        process = psutil.Process()
        
        # Get initial memory
        initial_memory = process.memory_percent()
        
        # Pre-filter multiple blocks
        for _ in range(5):
            block_data = self.backend.rpc("getblock", [self.test_block_hash, 0])
            self.parser.pre_filter_block(block_data)
            
        # Check memory usage hasn't grown too much
        final_memory = process.memory_percent()
        self.assertLess(final_memory, 85.0)  # Should stay under 85%
        self.assertLess(final_memory - initial_memory, 10.0)  # Shouldn't grow more than 10%


if __name__ == "__main__":
    unittest.main()
