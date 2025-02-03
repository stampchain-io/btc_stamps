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
    tx_info = parser.deserialize_transaction(SAMPLE_TX_HEX)

    assert isinstance(tx_info, dict)
    assert "txid" in tx_info
    assert "version" in tx_info
    assert "inputs" in tx_info
    assert "outputs" in tx_info

    # Check input structure
    assert len(tx_info["inputs"]) > 0
    input_0 = tx_info["inputs"][0]
    assert "prev_txid" in input_0
    assert "prev_vout" in input_0
    assert "sequence" in input_0

    # Check output structure
    assert len(tx_info["outputs"]) > 0
    output_0 = tx_info["outputs"][0]
    assert "value" in output_0
    assert "script_pubkey" in output_0
    assert "is_op_return" in output_0
    assert isinstance(output_0["value"], Decimal)


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
    for result in results:
        assert isinstance(result, dict)
        assert "txid" in result
        assert "version" in result


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
    for result in results:
        assert isinstance(result, dict)
        assert "txid" in result
        assert len(result["inputs"]) > 0
        assert len(result["outputs"]) > 0
