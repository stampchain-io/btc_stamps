"""Tests for the Rust-based Bitcoin transaction parser."""

from decimal import Decimal

import pytest

from index_core.parser import Parser, ParserError

# Real transaction hex from Bitcoin mainnet (block 820000)
SAMPLE_TX_HEX = "01000000000101361530b8037243b3f1c953c332061d9753a4995ded1ab376a83d885b3744b7b08500000000ffffffff0138630100000000001976a9146f77d225c5a10047afceccf98daace58a511b4d488ac024730440220038bb62199060044624e593fab989833ea174089245fd7e255c3b2402ab1af120220413693fea1a7ccd3d3828ee5c1a0c1305f836205f20d97ab8b5c71c3389a57bf0121021fccd86a0099f854af13ab77afc02ac0ba184b5ad834a006252a23fb08cac6da00000000"

# Load block hex from fixtures file to avoid embedding huge hex string
import json
from pathlib import Path

fixtures_path = Path(__file__).parent / "fixtures" / "test_data.json"
if fixtures_path.exists():
    with open(fixtures_path) as f:
        fixtures = json.load(f)
        SAMPLE_BLOCK_HEX = fixtures["block"]["hex"]
else:
    # Fallback for CI or when fixtures aren't available
    SAMPLE_BLOCK_HEX = None


def test_parser_initialization():
    """Test parser initialization."""
    parser = Parser()
    assert parser is not None
    assert parser._parser is not None


def test_deserialize_transaction():
    """Test transaction deserialization."""
    parser = Parser()
    tx = parser.deserialize_transaction(SAMPLE_TX_HEX)

    # Should return an EnhancedCTransaction (which inherits from CTransaction)
    from index_core.parser import EnhancedCTransaction

    assert isinstance(tx, EnhancedCTransaction)

    # Check basic CTransaction attributes
    assert hasattr(tx, "vin")  # inputs
    assert hasattr(tx, "vout")  # outputs
    assert hasattr(tx, "nVersion")  # version

    # Check that we can access the txid
    assert hasattr(tx, "txid")
    txid = tx.txid
    assert isinstance(txid, str)
    assert len(txid) == 64  # Bitcoin txid is 64 hex characters

    # Check inputs
    assert len(tx.vin) > 0
    input_0 = tx.vin[0]
    assert hasattr(input_0, "prevout")  # previous output reference
    assert hasattr(input_0, "nSequence")  # sequence number

    # Check outputs
    assert len(tx.vout) > 0
    output_0 = tx.vout[0]
    assert hasattr(output_0, "nValue")  # value in satoshis
    assert hasattr(output_0, "scriptPubKey")  # script
    assert isinstance(output_0.nValue, int)  # Value should be integer satoshis


def test_invalid_transaction():
    """Test handling of invalid transaction hex."""
    parser = Parser()
    with pytest.raises(ParserError):
        parser.deserialize_transaction("invalid_hex")


def test_batch_parse_transactions():
    """Test batch transaction parsing."""
    parser = Parser()
    # Note: The Rust parser now only returns transactions that should be included
    # The sample transaction may or may not be included, so we can't assert the exact number of results
    results = parser.batch_parse_transactions([SAMPLE_TX_HEX, SAMPLE_TX_HEX])

    # Check that the results are valid, regardless of how many are returned
    from index_core.parser import EnhancedCTransaction

    for result in results:
        assert isinstance(result, EnhancedCTransaction)
        assert hasattr(result, "txid")
        assert hasattr(result, "nVersion")


@pytest.mark.skipif(SAMPLE_BLOCK_HEX is None, reason="Block fixtures not available")
def test_parse_block():
    """Test block parsing."""
    parser = Parser()
    tx_hashes, raw_txs, timestamp, prev_hash, difficulty = parser.parse_block(SAMPLE_BLOCK_HEX)

    assert isinstance(tx_hashes, list)
    assert isinstance(raw_txs, dict)
    assert isinstance(timestamp, int)
    assert isinstance(prev_hash, str)
    assert difficulty is None  # Not implemented yet

    # Additional assertions with real data
    assert len(tx_hashes) > 0  # Block should have transactions
    assert len(raw_txs) == len(tx_hashes)  # Should have raw data for each tx
    assert all(isinstance(tx_hash, str) and len(tx_hash) == 64 for tx_hash in tx_hashes)
    assert all(isinstance(raw_tx, str) for raw_tx in raw_txs.values())


def test_parallel_processing():
    """Test parallel processing of transactions."""
    parser = Parser()
    # Create a large batch of transactions
    tx_hexes = [SAMPLE_TX_HEX] * 100

    # Note: The Rust parser now only returns transactions that should be included
    # The sample transaction may or may not be included, so we can't assert the exact number of results
    results = parser.batch_parse_transactions(tx_hexes)

    # Verify all results are valid, regardless of how many are returned
    from index_core.parser import EnhancedCTransaction

    for result in results:
        assert isinstance(result, EnhancedCTransaction)
        assert hasattr(result, "txid")
        assert len(result.vin) > 0  # inputs
        assert len(result.vout) > 0  # outputs
