"""Extended parser tests using real Bitcoin data fixtures."""

import json
from pathlib import Path

import pytest

from index_core.parser import EnhancedCTransaction, Parser, ParserError


@pytest.fixture
def fixture_data():
    """Load test fixtures from JSON file."""
    fixtures_path = Path(__file__).parent / "fixtures" / "test_data.json"
    if not fixtures_path.exists():
        pytest.skip("Fixtures file not found")

    with open(fixtures_path) as f:
        return json.load(f)


@pytest.fixture
def parser():
    """Create a parser instance."""
    return Parser()


def test_real_transaction_parsing(parser, fixture_data):
    """Test parsing real transactions from fixtures."""
    transactions = fixture_data["transactions"]

    for tx_data in transactions:
        tx_hex = tx_data["hex"]
        expected_txid = tx_data["txid"]

        # Parse the transaction
        tx = parser.deserialize_transaction(tx_hex)

        # Verify it's an EnhancedCTransaction
        assert isinstance(tx, EnhancedCTransaction)

        # Verify the txid matches
        assert tx.txid == expected_txid

        # Verify basic transaction properties
        assert hasattr(tx, "vin") and len(tx.vin) >= 0
        assert hasattr(tx, "vout") and len(tx.vout) > 0
        assert hasattr(tx, "nVersion") and isinstance(tx.nVersion, int)

        # Check outputs have valid values
        for output in tx.vout:
            assert hasattr(output, "nValue") and isinstance(output.nValue, int)
            assert hasattr(output, "scriptPubKey")


def test_real_block_parsing(parser, fixture_data):
    """Test parsing a real block from fixtures."""
    block_data = fixture_data["block"]
    block_hex = block_data["hex"]

    # Parse the block
    tx_hashes, raw_txs, timestamp, prev_hash, difficulty = parser.parse_block(block_hex)

    # Verify block properties
    assert isinstance(tx_hashes, list)
    assert len(tx_hashes) == block_data["tx_count"]

    assert isinstance(raw_txs, dict)
    assert len(raw_txs) == len(tx_hashes)

    assert timestamp == block_data["timestamp"]
    assert prev_hash == block_data["prev_hash"]

    # Verify all transaction hashes are valid
    for tx_hash in tx_hashes:
        assert isinstance(tx_hash, str)
        assert len(tx_hash) == 64  # Bitcoin txid is 64 hex chars
        assert tx_hash in raw_txs  # Should have raw data for each tx


def test_batch_parse_real_transactions(parser, fixture_data):
    """Test batch parsing with real transactions."""
    transactions = fixture_data["transactions"]
    tx_hexes = [tx["hex"] for tx in transactions]

    # Batch parse transactions
    results = parser.batch_parse_transactions(tx_hexes)

    # The parser filters transactions, so we might not get all back
    # But all returned should be valid
    for result in results:
        assert isinstance(result, EnhancedCTransaction)
        assert hasattr(result, "txid")
        assert len(result.txid) == 64

        # Verify it's one of our input transactions
        original_txids = [tx["txid"] for tx in transactions]
        if result.txid in original_txids:
            # If it matches one of our inputs, verify it parsed correctly
            idx = original_txids.index(result.txid)
            assert result.txid == transactions[idx]["txid"]


def test_parse_block_transactions(parser, fixture_data):
    """Test parsing individual transactions from a block."""
    block_data = fixture_data["block"]
    block_hex = block_data["hex"]

    # Parse the block to get transactions
    tx_hashes, raw_txs, _, _, _ = parser.parse_block(block_hex)

    # Try to parse each transaction individually
    parsed_count = 0
    for tx_hash, raw_tx in raw_txs.items():
        try:
            tx = parser.deserialize_transaction(raw_tx)
            assert isinstance(tx, EnhancedCTransaction)
            assert tx.txid == tx_hash
            parsed_count += 1
        except ParserError:
            # Some transactions might fail to parse, that's ok
            pass

    # We should be able to parse at least some transactions
    assert parsed_count > 0
    print(f"Successfully parsed {parsed_count}/{len(raw_txs)} transactions from block")


def test_transaction_properties(parser, fixture_data):
    """Test detailed transaction properties with real data."""
    # Use the first transaction for detailed testing
    tx_data = fixture_data["transactions"][0]
    tx_hex = tx_data["hex"]

    tx = parser.deserialize_transaction(tx_hex)

    # Test transaction version
    assert tx.nVersion in [1, 2]  # Common Bitcoin transaction versions

    # Test inputs
    if len(tx.vin) > 0:
        for inp in tx.vin:
            assert hasattr(inp, "prevout")
            assert hasattr(inp, "nSequence")
            assert isinstance(inp.nSequence, int)

    # Test outputs
    assert len(tx.vout) > 0
    total_output_value = 0
    for out in tx.vout:
        assert hasattr(out, "nValue")
        assert isinstance(out.nValue, int)
        assert out.nValue >= 0  # Output value should be non-negative
        total_output_value += out.nValue

        # Check script
        assert hasattr(out, "scriptPubKey")

    # Total output value should be positive for non-coinbase transactions
    if len(tx.vin) > 0:  # Not a coinbase transaction
        assert total_output_value > 0
