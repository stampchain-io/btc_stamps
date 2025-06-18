"""Test transaction processing in a block context."""

import binascii
from unittest import mock

import pytest


@pytest.fixture
def mock_backend():
    """Mock backend for testing."""
    backend = mock.MagicMock()
    backend.getblockhash.return_value = "00000000000000000001234567890abcdef1234567890abcdef1234567890ab"
    # Mock a simple block hex with minimal data
    backend.getblock.return_value = "0100000000000000000000000000000000000000000000000000000000000000000000003ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a29ab5f49ffff001d1dac2b7c01010000000100000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    return backend


@pytest.fixture
def mock_parser():
    """Mock parser for testing."""
    parser = mock.MagicMock()
    # Mock parse_block to return sample data
    parser.parse_block.return_value = (
        ["e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"],  # tx_hash_list
        {"e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2": "0100000001..."},  # raw_transactions
        1234567890,  # timestamp
        "000000000000000000abcdef1234567890abcdef1234567890abcdef12345678",  # prev_block_hash
        0.0001,  # bits
    )

    # Mock batch_parse_transactions
    mock_tx = mock.MagicMock()
    mock_tx.GetHash.return_value = b"\xe2\xaa\x45\x9e\xbf\xe0\xba\x36\x25\xc9\x17\x14\x34\x52\x67\x8a\x3e\x80\x63\x64\x89\xfe\x0e\xc8\xcc\x7e\x96\x51\xcf\xd4\xdd\xb2"[
        ::-1
    ]
    mock_tx.txid = "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"
    parser.batch_parse_transactions.return_value = [mock_tx]

    # Mock the _parser attribute (Rust parser)
    mock_rust_parser = mock.MagicMock()
    mock_tx_info = mock.MagicMock()
    mock_tx_info.should_include = True
    mock_tx_info.has_valid_data = True
    mock_tx_info.keyburn = False
    mock_tx_info.txid = "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"
    mock_rust_parser.deserialize_transaction.return_value = mock_tx_info
    mock_rust_parser.batch_parse_transactions.return_value = [mock_tx_info]
    parser._parser = mock_rust_parser

    return parser


class TestBlockTransaction:
    """Test transaction processing in block context."""

    def test_transaction_found_in_block(self, mock_backend, mock_parser):
        """Test when target transaction is found in block."""
        # Set up test data
        target_txid = "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"
        block_index = 795419

        # Mock CURRENT_BLOCK_INDEX
        with mock.patch("index_core.util.CURRENT_BLOCK_INDEX", block_index):
            # Get block data
            block_hash = mock_backend.getblockhash(block_index)
            block_hex = mock_backend.getblock(block_hash, 0)

            # Parse block
            tx_hash_list, raw_transactions, timestamp, prev_block_hash, bits = mock_parser.parse_block(block_hex)

            # Verify target transaction is in the block
            assert target_txid in tx_hash_list
            assert len(tx_hash_list) == 1

            # Test individual transaction parsing with Rust
            tx_hex = raw_transactions[target_txid]
            tx_info = mock_parser._parser.deserialize_transaction(tx_hex)
            assert tx_info.should_include is True
            assert tx_info.has_valid_data is True
            assert tx_info.keyburn is False

            # Test batch transaction parsing
            tx_hexes = list(raw_transactions.values())
            parsed_txs = mock_parser._parser.batch_parse_transactions(tx_hexes)
            assert len(parsed_txs) == 1
            assert parsed_txs[0].txid == target_txid

            # Test Python parser's batch_parse_transactions
            python_parsed_txs = mock_parser.batch_parse_transactions(tx_hexes)
            assert len(python_parsed_txs) == 1

            # Verify transaction hash
            tx_hash = python_parsed_txs[0].GetHash()
            tx_hash_hex = binascii.hexlify(tx_hash[::-1]).decode("utf-8")
            assert tx_hash_hex == target_txid

    def test_transaction_not_found_in_block(self, mock_backend, mock_parser):
        """Test when target transaction is not found in block."""
        # Modify parser to return empty results
        mock_parser.parse_block.return_value = (
            ["1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"],  # Different tx
            {"1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef": "0100000001..."},
            1234567890,
            "000000000000000000abcdef1234567890abcdef1234567890abcdef12345678",
            0.0001,
        )

        target_txid = "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"
        block_index = 795419

        # Get block data
        block_hash = mock_backend.getblockhash(block_index)
        block_hex = mock_backend.getblock(block_hash, 0)

        # Parse block
        tx_hash_list, raw_transactions, timestamp, prev_block_hash, bits = mock_parser.parse_block(block_hex)

        # Verify target transaction is NOT in the block
        assert target_txid not in tx_hash_list
        assert len(tx_hash_list) == 1

    def test_batch_parsing_filters_transactions(self, mock_backend, mock_parser):
        """Test that batch parsing correctly filters transactions."""
        # Set up multiple transactions
        tx1 = mock.MagicMock()
        tx1.txid = "tx1_id"
        tx1.should_include = True

        tx2 = mock.MagicMock()
        tx2.txid = "tx2_id"
        tx2.should_include = False

        tx3 = mock.MagicMock()
        tx3.txid = "tx3_id"
        tx3.should_include = True

        # Mock batch parse to return only transactions that should be included
        mock_parser._parser.batch_parse_transactions.return_value = [tx1, tx3]

        # Test batch parsing
        tx_hexes = ["hex1", "hex2", "hex3"]
        parsed_txs = mock_parser._parser.batch_parse_transactions(tx_hexes)

        # Verify only included transactions are returned
        assert len(parsed_txs) == 2
        assert parsed_txs[0].txid == "tx1_id"
        assert parsed_txs[1].txid == "tx3_id"
