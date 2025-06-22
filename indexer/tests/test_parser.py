"""Tests for parser module."""

import unittest
from unittest.mock import MagicMock, patch

from index_core.parser import Parser, ParserError


class TestParser(unittest.TestCase):
    """Test parser functionality."""

    def test_parser_initialization(self):
        """Test that Parser can be initialized."""
        try:
            parser = Parser()
            self.assertIsNotNone(parser)
        except ParserError as e:
            # It's OK if Rust parser is not available in test environment
            self.assertIn("Rust parser not available", str(e))

    def test_parser_singleton(self):
        """Test that Parser follows singleton pattern."""
        try:
            parser1 = Parser()
            parser2 = Parser()
            self.assertIs(parser1, parser2)
        except ParserError:
            # Skip if Rust parser is not available
            self.skipTest("Rust parser not available")

    @patch('index_core.parser.RUST_PARSER_AVAILABLE', False)
    def test_parser_initialization_without_rust(self):
        """Test parser initialization when Rust parser is not available."""
        # Reset singleton for this test
        Parser._instance = None
        
        with self.assertRaises(ParserError) as context:
            Parser()
        
        self.assertIn("Rust parser not available", str(context.exception))

    @patch('index_core.parser.RUST_PARSER_AVAILABLE', True)
    @patch('index_core.parser.FastTransactionParser')
    def test_parser_initialization_with_rust(self, mock_fast_parser):
        """Test parser initialization when Rust parser is available."""
        # Reset singleton for this test
        Parser._instance = None
        
        # Mock the FastTransactionParser
        mock_instance = MagicMock()
        mock_fast_parser.return_value = mock_instance
        
        parser = Parser()
        self.assertIsNotNone(parser)
        self.assertEqual(parser._parser, mock_instance)
        mock_fast_parser.assert_called_once()

    @patch('index_core.parser.RUST_PARSER_AVAILABLE', True)
    @patch('index_core.parser.FastTransactionParser')
    def test_deserialize_transaction(self, mock_fast_parser):
        """Test deserialize_transaction method."""
        # Reset singleton for this test
        Parser._instance = None
        
        # Mock the Rust parser
        mock_parser_instance = MagicMock()
        mock_fast_parser.return_value = mock_parser_instance
        
        # Mock transaction info
        mock_tx_info = MagicMock()
        mock_tx_info.txid = "test_txid"
        mock_tx_info.version = 1
        mock_tx_info.inputs = []
        mock_tx_info.outputs = []
        mock_tx_info.should_include = True
        mock_tx_info.has_valid_data = True
        mock_tx_info.keyburn = False
        
        mock_parser_instance.deserialize_transaction.return_value = mock_tx_info
        
        parser = Parser()
        tx_hex = "01000000000000000000"
        
        with patch.object(parser, '_convert_to_ctransaction') as mock_convert:
            mock_ctx = MagicMock()
            mock_convert.return_value = mock_ctx
            
            result = parser.deserialize_transaction(tx_hex)
            
            mock_parser_instance.deserialize_transaction.assert_called_once_with(tx_hex)
            mock_convert.assert_called_once_with(mock_tx_info)
            self.assertEqual(result, mock_ctx)

    @patch('index_core.parser.RUST_PARSER_AVAILABLE', True)
    @patch('index_core.parser.FastTransactionParser')
    def test_batch_parse_transactions(self, mock_fast_parser):
        """Test batch_parse_transactions method."""
        # Reset singleton for this test
        Parser._instance = None
        
        # Mock the Rust parser
        mock_parser_instance = MagicMock()
        mock_fast_parser.return_value = mock_parser_instance
        
        # Mock transaction infos
        mock_tx_info1 = MagicMock()
        mock_tx_info1.txid = "txid1"
        mock_tx_info1.version = 1
        mock_tx_info1.inputs = []
        mock_tx_info1.outputs = []
        
        mock_tx_info2 = MagicMock()
        mock_tx_info2.txid = "txid2"
        mock_tx_info2.version = 1
        mock_tx_info2.inputs = []
        mock_tx_info2.outputs = []
        
        mock_parser_instance.batch_parse_transactions.return_value = [mock_tx_info1, mock_tx_info2]
        
        parser = Parser()
        tx_hexes = ["hex1", "hex2", "hex3"]
        
        with patch.object(parser, '_convert_to_ctransaction') as mock_convert:
            mock_ctx1 = MagicMock()
            mock_ctx1.txid = "txid1"
            mock_ctx2 = MagicMock()
            mock_ctx2.txid = "txid2"
            mock_convert.side_effect = [mock_ctx1, mock_ctx2]
            
            results = parser.batch_parse_transactions(tx_hexes)
            
            self.assertEqual(len(results), 2)
            mock_parser_instance.batch_parse_transactions.assert_called()

    @patch('index_core.parser.RUST_PARSER_AVAILABLE', True)
    @patch('index_core.parser.FastTransactionParser')
    def test_parse_block(self, mock_fast_parser):
        """Test parse_block method."""
        # Reset singleton for this test
        Parser._instance = None
        
        # Mock the Rust parser
        mock_parser_instance = MagicMock()
        mock_fast_parser.return_value = mock_parser_instance
        
        # Mock block parsing result
        tx_hash_list = ["tx1", "tx2"]
        raw_transactions = {"tx1": "hex1", "tx2": "hex2"}
        timestamp = 1234567890
        prev_block_hash = "prev_hash"
        bits = 0x1a2b3c4d
        
        mock_parser_instance.parse_block.return_value = (
            tx_hash_list,
            raw_transactions,
            timestamp,
            prev_block_hash,
            bits
        )
        
        parser = Parser()
        block_hex = "block_hex_data"
        
        result = parser.parse_block(block_hex)
        
        mock_parser_instance.parse_block.assert_called_once_with(block_hex)
        self.assertEqual(result[0], tx_hash_list)
        self.assertEqual(result[1], raw_transactions)
        self.assertEqual(result[2], timestamp)
        self.assertEqual(result[3], prev_block_hash)
        self.assertEqual(result[4], bits)

    @patch('index_core.parser.RUST_PARSER_AVAILABLE', True)
    @patch('index_core.parser.FastTransactionParser')
    def test_garbage_collection(self, mock_fast_parser):
        """Test garbage collection methods."""
        # Reset singleton for this test
        Parser._instance = None
        
        # Mock the Rust parser
        mock_parser_instance = MagicMock()
        mock_fast_parser.return_value = mock_parser_instance
        
        parser = Parser()
        
        # Test _should_collect_garbage
        with patch.object(parser._process, 'memory_percent', return_value=90.0):
            should_gc = parser._should_collect_garbage()
            self.assertTrue(should_gc)
        
        with patch.object(parser._process, 'memory_percent', return_value=50.0):
            should_gc = parser._should_collect_garbage()
            self.assertFalse(should_gc)
        
        # Test _perform_garbage_collection
        with patch('index_core.parser.gc') as mock_gc:
            mock_gc.get_count.return_value = (10001, 1001, 101)
            with patch.object(parser._process, 'memory_percent', side_effect=[80.0, 70.0]):
                parser._perform_garbage_collection()
                mock_gc.collect.assert_called()


class TestEnhancedCTransaction(unittest.TestCase):
    """Test EnhancedCTransaction class."""

    @patch('index_core.parser.CTransaction')
    def test_enhanced_ctransaction_creation(self, mock_ctx_class):
        """Test creating an EnhancedCTransaction."""
        from index_core.parser import EnhancedCTransaction
        
        # Create a mock CTransaction instance
        mock_ctx = MagicMock()
        mock_ctx_class.return_value = mock_ctx
        
        # Test successful creation
        enhanced = EnhancedCTransaction(mock_ctx, txid="test_txid", custom_attr="value")
        self.assertEqual(enhanced._ctx, mock_ctx)
        self.assertEqual(enhanced._extra_attrs["txid"], "test_txid")
        self.assertEqual(enhanced._extra_attrs["custom_attr"], "value")

    def test_enhanced_ctransaction_invalid_input(self):
        """Test EnhancedCTransaction with invalid input."""
        from index_core.parser import EnhancedCTransaction
        
        # Test with non-CTransaction input
        with self.assertRaises(TypeError) as context:
            EnhancedCTransaction("not a transaction")
        
        self.assertIn("must be created with a CTransaction instance", str(context.exception))

    @patch('index_core.parser.CTransaction')
    def test_enhanced_ctransaction_attribute_access(self, mock_ctx_class):
        """Test attribute access in EnhancedCTransaction."""
        from index_core.parser import EnhancedCTransaction
        
        # Create a mock CTransaction with some attributes
        mock_ctx = MagicMock()
        mock_ctx.version = 1
        mock_ctx.nLockTime = 0
        mock_ctx_class.return_value = mock_ctx
        
        enhanced = EnhancedCTransaction(mock_ctx, txid="test_txid", custom_attr="value")
        
        # Test accessing extra attributes
        self.assertEqual(enhanced.txid, "test_txid")
        self.assertEqual(enhanced.custom_attr, "value")
        
        # Test accessing CTransaction attributes
        self.assertEqual(enhanced.version, 1)
        self.assertEqual(enhanced.nLockTime, 0)
        
        # Test accessing non-existent attribute
        with self.assertRaises(AttributeError):
            _ = enhanced.non_existent_attr


class TestParserError(unittest.TestCase):
    """Test ParserError exception."""

    def test_parser_error_creation(self):
        """Test creating ParserError."""
        from index_core.parser import ParserError
        
        error = ParserError("Test error message")
        self.assertEqual(str(error), "Test error message")
        self.assertIsInstance(error, Exception)


if __name__ == "__main__":
    unittest.main()