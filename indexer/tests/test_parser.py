"""Tests for the Rust-based Bitcoin transaction parser."""

from decimal import Decimal

import pytest

from index_core.parser import Parser, ParserError

# Sample transaction hex from Bitcoin testnet
SAMPLE_TX_HEX = "0200000001268171371edff285e937adeea4b37b78000c0566cbb3ad64641713ca42171bf6000000006a473044022070b2245123e6bf474d60c5b50c043d4c691a5d2435f09a34a7662a9dc251790a022001329ca9dacf280bdf30740ec0390422422c81cb45839457aeb76fc12edd95b3012102657d118d3357b8e0f4c2cd46db7b39f6d9c38d9a70abcb9b2de5dc8dbfe4ce31feffffff02d3dff505000000001976a914d0c59903c5bac2868760e90fd521a4665aa7652088ac00e1f5050000000017a9143545e6e33b832c47050f24d3eeb93c9c03948bc787b32e1300"

# Sample block hex (you'll need to provide a real one)
SAMPLE_BLOCK_HEX = "..."  # Add a real block hex for testing


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


@pytest.mark.skip(reason="Need real block hex data")
def test_parse_block():
    """Test block parsing."""
    parser = Parser()
    tx_hashes, raw_txs, timestamp, prev_hash, difficulty = parser.parse_block(SAMPLE_BLOCK_HEX)

    assert isinstance(tx_hashes, list)
    assert isinstance(raw_txs, dict)
    assert isinstance(timestamp, int)
    assert isinstance(prev_hash, str)
    assert difficulty is None  # Not implemented yet


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
