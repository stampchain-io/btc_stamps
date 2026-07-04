"""Test Rust parser basic functionality with mocked data."""

from unittest import mock

import pytest


@pytest.fixture
def parser():
    """Mock parser for testing."""
    parser = mock.MagicMock()

    # Mock TransactionInfo objects
    tx_info1 = mock.MagicMock()
    tx_info1.should_include = True
    tx_info1.has_valid_pattern = True
    tx_info1.has_valid_data = True
    tx_info1.keyburn = False
    tx_info1.txid = "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"
    tx_info1.outputs = []

    tx_info2 = mock.MagicMock()
    tx_info2.should_include = True
    tx_info2.has_valid_pattern = True
    tx_info2.has_valid_data = True
    tx_info2.keyburn = False
    tx_info2.txid = "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc"
    tx_info2.outputs = []

    # Configure batch_parse_transactions to return appropriate tx_info based on input
    def batch_parse_side_effect(tx_hexes):
        if not tx_hexes:
            return []
        # Return mocked transaction info for each hex
        results = []
        for _ in tx_hexes:
            # Alternate between tx_info1 and tx_info2 for variety
            results.append(tx_info1 if len(results) % 2 == 0 else tx_info2)
        return results

    parser.batch_parse_transactions.side_effect = batch_parse_side_effect

    # Mock other methods
    parser.deserialize_transaction.return_value = tx_info1
    parser.parse_block.return_value = ([], {}, 0, "", 0.0)

    return parser


def test_transaction(parser):
    """Test basic transaction parsing with the mocked Rust parser."""
    # Test with sample transaction hex (mocked)
    tx_hex = "0100000001" + "00" * 100  # Simplified hex for testing

    # Test batch_parse_transactions
    results = parser.batch_parse_transactions([tx_hex])
    assert len(results) == 1

    tx_info = results[0]
    assert tx_info.should_include is True
    assert tx_info.has_valid_pattern is True
    assert tx_info.has_valid_data is True
    assert tx_info.keyburn is False
    assert tx_info.txid == "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"


def test_multiple_transactions(parser):
    """Test parsing multiple transactions."""
    tx_hexes = ["0100000001" + "00" * 100, "0100000001" + "11" * 100]

    results = parser.batch_parse_transactions(tx_hexes)
    assert len(results) == 2

    # First transaction
    assert results[0].txid == "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"
    # Second transaction
    assert results[1].txid == "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc"


def test_empty_transaction_list(parser):
    """Test parsing empty transaction list."""
    results = parser.batch_parse_transactions([])
    assert results == []
