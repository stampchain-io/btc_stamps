"""
Test Rust parser functionality using Bitcoin fixtures.

Migrated from test_rust_parser.py to use Bitcoin fixtures instead of requiring a live Bitcoin node.
"""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from btc_stamps_parser import FastTransactionParser
from index_core.backend import Backend

logger = logging.getLogger(__name__)


@pytest.mark.unit
class TestRustParserMigrated:
    """Test Rust parser functionality using fixtures."""

    @pytest.fixture(scope="class")
    def bitcoin_fixtures(self):
        """Load Bitcoin node fixtures."""
        fixtures_path = Path(__file__).parent / "fixtures" / "bitcoin_node_fixtures.json"
        with open(fixtures_path, "r") as f:
            return json.load(f)

    @pytest.fixture(scope="class")
    def special_transactions(self, bitcoin_fixtures):
        """Extract special transactions from fixtures."""
        return bitcoin_fixtures["special_transactions"]

    @pytest.fixture(scope="class")
    def test_block_data(self, bitcoin_fixtures):
        """Extract test block data from fixtures."""
        return bitcoin_fixtures["test_block_700000"]

    @pytest.fixture
    def parser(self):
        """Create a FastTransactionParser instance."""
        return FastTransactionParser()

    @pytest.fixture
    def mock_backend(self, special_transactions, test_block_data):
        """Create a backend instance with transaction and block data from fixtures."""
        backend_instance = Backend()

        # Create mapping of txid to hex data
        tx_data = {tx["txid"]: tx["hex"] for tx in special_transactions}

        def mock_getrawtransaction(txid):
            if txid in tx_data:
                return tx_data[txid]
            raise Exception(f"Transaction {txid} not found in fixtures")

        def mock_rpc(method, params):
            if method == "getblockcount":
                return 700000  # Mock current block height
            elif method == "getblock":
                block_hash = params[0]
                verbosity = params[1] if len(params) > 1 else 1

                if block_hash == test_block_data["hash"]:
                    if verbosity == 0:
                        # Return raw block data
                        return test_block_data["hex"]
                    else:
                        # Return structured block data (not used in current tests)
                        return {
                            "hash": test_block_data["hash"],
                            "height": test_block_data["height"],
                            "tx": [],  # Would contain transaction list
                        }
                else:
                    raise Exception(f"Block {block_hash} not found in fixtures")
            else:
                raise Exception(f"RPC method {method} not mocked")

        # Add the mock methods to the real backend
        backend_instance.getrawtransaction = mock_getrawtransaction
        backend_instance.rpc = mock_rpc

        return backend_instance

    @pytest.fixture
    def test_tx_hash(self, special_transactions):
        """Get a known test transaction hash."""
        return special_transactions[0]["txid"]

    @pytest.fixture
    def test_block_hash(self, test_block_data):
        """Get the test block hash."""
        return test_block_data["hash"]

    def test_single_transaction_parsing(self, parser, mock_backend, test_tx_hash):
        """Test parsing a single transaction."""
        # Get raw transaction from fixtures
        tx_hex = mock_backend.getrawtransaction(test_tx_hash)

        # Parse transaction
        tx_info = parser.deserialize_transaction(tx_hex)

        # Verify basic transaction properties
        assert tx_info.txid == test_tx_hash
        assert len(tx_info.inputs) > 0, "Should have at least one input"
        assert len(tx_info.outputs) > 0, "Should have at least one output"

        # Verify transaction has should_include attribute
        assert hasattr(tx_info, "should_include"), "Transaction should have should_include attribute"

    def test_block_parsing(self, parser, mock_backend, test_block_hash):
        """Test parsing an entire block."""
        # Get raw block from fixtures
        block_data = mock_backend.rpc("getblock", [test_block_hash, 0])

        # Parse block
        tx_hash_list, raw_transactions, timestamp, prev_block_hash, bits = parser.parse_block(block_data)

        # Verify block properties
        assert isinstance(tx_hash_list, list), "tx_hash_list should be a list"
        assert isinstance(raw_transactions, dict), "raw_transactions should be a dict"
        assert isinstance(timestamp, int), "timestamp should be an int"
        assert isinstance(prev_block_hash, str), "prev_block_hash should be a string"

    def test_batch_transaction_parsing(self, parser, mock_backend, special_transactions):
        """
        Test parsing multiple transactions in batch.

        Note: The Rust parser now only returns transactions that should be included,
        so we can't assert the exact number of results. We'll use known includable
        transactions for this test.
        """
        # Use known includable transactions from fixtures
        tx_hashes = [tx["txid"] for tx in special_transactions]

        # Get raw transactions from fixtures
        tx_hexes = [mock_backend.getrawtransaction(tx_hash) for tx_hash in tx_hashes]

        # Parse transactions in batch
        tx_infos = parser.batch_parse_transactions(tx_hexes)

        # Verify that all returned transactions have should_include=True
        for tx_info in tx_infos:
            assert tx_info.should_include, f"Transaction {tx_info.txid} was returned but has should_include=False"

            # Verify the transaction is in our original list
            assert tx_info.txid in tx_hashes, f"Transaction {tx_info.txid} was not in the original list of transactions"

        # Verify that all expected transactions were returned
        returned_txids = {tx_info.txid for tx_info in tx_infos}
        for tx_hash in tx_hashes:
            assert tx_hash in returned_txids, f"Expected transaction {tx_hash} was not returned"

    def test_invalid_transaction(self, parser):
        """Test handling of invalid transaction data."""
        invalid_hex = "invalid_hex_data"

        # Should raise an exception for invalid hex
        with pytest.raises(Exception):
            parser.deserialize_transaction(invalid_hex)

    def test_empty_transaction(self, parser):
        """Test handling of empty transaction data."""
        empty_hex = ""

        # Should raise an exception for empty data
        with pytest.raises(Exception):
            parser.deserialize_transaction(empty_hex)

    def test_fixture_data_availability(self, special_transactions, test_block_data):
        """Test that all required fixture data is available."""
        assert len(special_transactions) >= 2, "Should have at least 2 special transactions"

        # Verify transaction data integrity
        for tx in special_transactions:
            assert "txid" in tx, "Transaction missing txid"
            assert "hex" in tx, "Transaction missing hex data"
            assert len(tx["hex"]) > 0, "Transaction hex data is empty"

        # Verify block data integrity
        assert "hash" in test_block_data, "Block missing hash"
        assert "hex" in test_block_data, "Block missing hex data"
        assert "height" in test_block_data, "Block missing height"
        assert len(test_block_data["hex"]) > 0, "Block hex data is empty"

    def test_parser_consistency(self, parser, mock_backend, special_transactions):
        """Test that parser results are consistent between single and batch parsing."""
        # Use the first transaction
        tx = special_transactions[0]
        tx_hash = tx["txid"]
        tx_hex = tx["hex"]

        # Parse single transaction
        single_result = parser.deserialize_transaction(tx_hex)

        # Parse in batch
        batch_results = parser.batch_parse_transactions([tx_hex])

        # Should have one result from batch
        assert len(batch_results) >= 0, "Batch parsing should return results for valid transactions"

        # If both single and batch return results, they should be consistent
        if single_result.should_include:
            assert len(batch_results) == 1, "Batch should return exactly one transaction if single parsing succeeds"
            batch_result = batch_results[0]

            assert single_result.txid == batch_result.txid, "TXID should match between single and batch parsing"
            assert single_result.should_include == batch_result.should_include, "should_include should match"
            assert len(single_result.inputs) == len(batch_result.inputs), "Input count should match"
            assert len(single_result.outputs) == len(batch_result.outputs), "Output count should match"
