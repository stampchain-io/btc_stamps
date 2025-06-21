"""
Test that special transactions are correctly identified by both Python and Rust implementations.

Migrated from test_special_txs.py to use Bitcoin fixtures instead of requiring a live Bitcoin node.

These test cases verify that both implementations correctly identify transactions that should be included
in the indexing process. The transactions used in these tests represent important edge cases that help
ensure compatibility and correctness between the Python and Rust implementations.

For detailed information about these test transactions, see the documentation in:
indexer/docs/rust-python-parser-issues.md
"""

import json
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import index_core.backend as backend
from index_core.transaction_utils import quick_filter_src20_transaction

# Configure logging
logging.basicConfig(level=logging.DEBUG if os.environ.get("RUST_LOG") == "debug" else logging.INFO)
logger = logging.getLogger(__name__)


@pytest.mark.unit
class TestSpecialTransactionsMigrated:
    """
    Test that special transactions are correctly identified using Bitcoin fixtures.

    Migrated from test_special_txs.py to use fixtures instead of requiring a live Bitcoin node.
    """

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

    @pytest.fixture
    def mock_backend(self, special_transactions):
        """Create a backend instance with transaction data from fixtures."""
        # Use real backend instance for proper deserialization
        backend_instance = backend.Backend()

        # Create mapping of txid to hex data
        tx_data = {tx["txid"]: tx["hex"] for tx in special_transactions}

        def mock_getrawtransaction(txid):
            if txid in tx_data:
                return tx_data[txid]
            raise Exception(f"Transaction {txid} not found in fixtures")

        # Add the mock method to the real backend
        backend_instance.getrawtransaction = mock_getrawtransaction

        return backend_instance

    @pytest.fixture
    def special_txids(self, special_transactions):
        """Get the list of special transaction IDs."""
        return [tx["txid"] for tx in special_transactions]

    def test_python_implementation(self, mock_backend, special_txids):
        """
        Test that the Python implementation correctly identifies the special transactions.

        This test verifies that the Python implementation's quick_filter_src20_transaction function
        correctly identifies transactions that should be included in the indexing process.
        """
        for txid in special_txids:
            # Fetch the raw transaction hex from fixtures
            tx_hex = mock_backend.getrawtransaction(txid)

            # Deserialize the transaction
            ctx = mock_backend.deserialize(tx_hex)

            # Check if the transaction should be included
            should_include = quick_filter_src20_transaction(ctx)

            logger.info(f"Python implementation: Transaction {txid} should_include = {should_include}")
            assert should_include, f"Python implementation failed to include transaction {txid}"

    def test_rust_implementation(self, mock_backend, special_txids):
        """
        Test that the Rust implementation correctly identifies the special transactions.

        This test verifies that the Rust implementation's deserialize_transaction function
        correctly identifies transactions that should be included in the indexing process.

        Note: This test accesses the Rust parser directly to get the should_include attribute,
        bypassing the conversion to CTransaction which would lose this attribute.
        """
        # Create a mock backend with Rust parser
        backend_instance = backend.Backend()

        if not hasattr(backend_instance, "_parser") or backend_instance._parser is None:
            pytest.skip("Rust parser not available")

        # Access the Rust parser directly
        rust_parser = backend_instance._parser._parser

        for txid in special_txids:
            # Fetch the raw transaction hex from fixtures
            tx_hex = mock_backend.getrawtransaction(txid)

            # Parse the transaction with the Rust parser directly
            tx_info = rust_parser.deserialize_transaction(tx_hex)

            logger.info(f"Rust implementation: Transaction {txid} should_include = {tx_info.should_include}")
            assert tx_info.should_include, f"Rust implementation failed to include transaction {txid}"

    def test_batch_processing(self, mock_backend, special_txids):
        """
        Test that the Rust batch processing correctly identifies the special transactions.

        This test verifies that the Rust implementation's batch_parse_transactions function
        correctly identifies transactions that should be included in the indexing process
        when processing multiple transactions in a batch.

        Note: The Rust parser now only returns transactions that should be included,
        so we expect all returned transactions to have should_include=True.
        """
        # Create a mock backend with Rust parser
        backend_instance = backend.Backend()

        if not hasattr(backend_instance, "_parser") or backend_instance._parser is None:
            pytest.skip("Rust parser not available")

        # Access the Rust parser directly
        rust_parser = backend_instance._parser._parser

        # Create a list of transaction hexes from fixtures
        tx_hexes = [mock_backend.getrawtransaction(txid) for txid in special_txids]

        # Process the transactions in batch
        parsed_txs = rust_parser.batch_parse_transactions(tx_hexes)

        # Check that all special transactions were included
        # The Rust parser now only returns transactions that should be included
        assert len(parsed_txs) == len(
            special_txids
        ), f"Expected {len(special_txids)} transactions to be included, got {len(parsed_txs)}"

        # Verify that all returned transactions have should_include=True
        for tx_info in parsed_txs:
            assert tx_info.should_include, f"Transaction {tx_info.txid} was returned but has should_include=False"

        # Verify that all special transactions are in the returned set
        returned_txids = {tx_info.txid for tx_info in parsed_txs}
        for txid in special_txids:
            assert txid in returned_txids, f"Special transaction {txid} was not included in the results"

    def test_fixture_data_integrity(self, special_transactions):
        """Test that fixture data is complete and valid."""
        assert len(special_transactions) == 2, "Expected exactly 2 special transactions in fixtures"

        expected_txids = [
            "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2",
            "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc",
        ]

        actual_txids = [tx["txid"] for tx in special_transactions]
        assert set(actual_txids) == set(expected_txids), f"Fixture TXIDs {actual_txids} don't match expected {expected_txids}"

        # Verify each transaction has required fields
        for tx in special_transactions:
            assert "txid" in tx, "Transaction missing txid"
            assert "hex" in tx, "Transaction missing hex data"
            assert "description" in tx, "Transaction missing description"
            assert len(tx["hex"]) > 0, "Transaction hex data is empty"
