"""Tests for the fast_parser module."""

from unittest.mock import Mock, patch

import pytest


class TestFastParser:
    """Test cases for FastParser class."""

    @patch("index_core.fast_parser.FastTransactionParser")
    def test_init(self, mock_parser_class):
        """Test FastParser initialization."""
        from index_core.fast_parser import FastParser

        mock_instance = Mock()
        mock_parser_class.return_value = mock_instance

        parser = FastParser()

        assert parser._parser == mock_instance
        mock_parser_class.assert_called_once()

    @patch("index_core.fast_parser.FastTransactionParser")
    def test_deserialize_transaction(self, mock_parser_class):
        """Test deserialize_transaction method."""
        from index_core.fast_parser import FastParser

        # Mock the Rust parser
        mock_parser_instance = Mock()
        mock_tx_info = Mock()
        mock_parser_instance.deserialize_transaction.return_value = mock_tx_info
        mock_parser_class.return_value = mock_parser_instance

        parser = FastParser()
        tx_hex = "0100000001abcd..."
        result = parser.deserialize_transaction(tx_hex)

        assert result == mock_tx_info
        mock_parser_instance.deserialize_transaction.assert_called_once_with(tx_hex)

    @patch("index_core.fast_parser.FastTransactionParser")
    def test_batch_parse_transactions(self, mock_parser_class):
        """Test batch_parse_transactions method."""
        from index_core.fast_parser import FastParser

        # Mock the Rust parser
        mock_parser_instance = Mock()
        mock_tx_infos = [Mock(), Mock(), Mock()]
        mock_parser_instance.batch_parse_transactions.return_value = mock_tx_infos
        mock_parser_class.return_value = mock_parser_instance

        parser = FastParser()
        tx_hexes = ["hex1", "hex2", "hex3"]
        result = parser.batch_parse_transactions(tx_hexes)

        assert result == mock_tx_infos
        mock_parser_instance.batch_parse_transactions.assert_called_once_with(tx_hexes)

    @patch("index_core.fast_parser.FastTransactionParser")
    def test_parse_block_success(self, mock_parser_class):
        """Test successful block parsing."""
        from index_core.fast_parser import FastParser

        # Mock the Rust parser return value
        mock_parser_instance = Mock()
        expected_result = (
            ["tx1", "tx2"],  # tx_hash_list
            {"tx1": "hex1", "tx2": "hex2"},  # raw_transactions
            1234567890,  # timestamp
            "prev_block_hash",  # prev_block_hash
            0.5,  # bits
        )
        mock_parser_instance.parse_block.return_value = expected_result
        mock_parser_class.return_value = mock_parser_instance

        parser = FastParser()
        block_hex = "block_hex_data"
        result = parser.parse_block(block_hex)

        assert result == expected_result
        mock_parser_instance.parse_block.assert_called_once_with(block_hex)

    @patch("index_core.fast_parser.logger")
    @patch("index_core.fast_parser.FastTransactionParser")
    def test_parse_block_error(self, mock_parser_class, mock_logger):
        """Test parse_block error handling."""
        from index_core.fast_parser import FastParser

        # Mock the Rust parser to raise an exception
        mock_parser_instance = Mock()
        error_msg = "Invalid block format"
        mock_parser_instance.parse_block.side_effect = Exception(error_msg)
        mock_parser_class.return_value = mock_parser_instance

        parser = FastParser()
        block_hex = "invalid_block_hex"

        with pytest.raises(Exception) as exc_info:
            parser.parse_block(block_hex)

        assert str(exc_info.value) == error_msg
        mock_logger.error.assert_called_once_with(f"Error parsing block: {error_msg}")

    @patch("index_core.fast_parser.FastTransactionParser")
    def test_parse_block_return_types(self, mock_parser_class):
        """Test that parse_block returns correct types."""
        from index_core.fast_parser import FastParser

        # Mock realistic return values
        mock_parser_instance = Mock()
        expected_result = (
            ["0x123", "0x456"],  # List of transaction hashes
            {"0x123": "01000000...", "0x456": "01000000..."},  # Dict of tx hash to hex
            1609459200,  # Unix timestamp
            "0x00000000000000000007c4b8e3c3b7f4a5d6e8f9a1b2c3d4e5f6a7b8c9d0e1f2",  # Previous block hash
            404472624.0,  # Block bits as float
        )
        mock_parser_instance.parse_block.return_value = expected_result
        mock_parser_class.return_value = mock_parser_instance

        parser = FastParser()
        result = parser.parse_block("block_hex")

        # Verify types
        assert isinstance(result[0], list)
        assert isinstance(result[1], dict)
        assert isinstance(result[2], int)
        assert isinstance(result[3], str)
        assert isinstance(result[4], float)
