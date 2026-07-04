"""
Test the Bitcoin fixtures loader utility.
"""

import pytest

from tests.bitcoin_fixtures_loader import BitcoinFixturesLoader, get_special_transaction_hex, get_test_block_hex


@pytest.mark.unit
class TestBitcoinFixturesLoader:
    """Test Bitcoin fixtures loader functionality."""

    @pytest.fixture
    def loader(self):
        """Create a fixtures loader instance."""
        return BitcoinFixturesLoader()

    def test_load_fixtures(self, loader):
        """Test that fixtures can be loaded."""
        fixtures_data = loader.fixtures_data
        assert isinstance(fixtures_data, dict)
        assert "special_transactions" in fixtures_data
        assert "test_block_700000" in fixtures_data

    def test_get_special_transactions(self, loader):
        """Test getting special transactions."""
        special_txs = loader.get_special_transactions()
        assert isinstance(special_txs, list)
        assert len(special_txs) >= 2

        # Check that each transaction has required fields
        for tx in special_txs:
            assert "txid" in tx
            assert "hex" in tx
            assert "description" in tx

    def test_get_special_transaction(self, loader):
        """Test getting a specific special transaction."""
        # Get the first transaction
        special_txs = loader.get_special_transactions()
        test_txid = special_txs[0]["txid"]

        # Retrieve it specifically
        tx = loader.get_special_transaction(test_txid)
        assert tx is not None
        assert tx["txid"] == test_txid

        # Test non-existent transaction
        non_existent = loader.get_special_transaction("nonexistent")
        assert non_existent is None

    def test_get_special_transaction_hex(self, loader):
        """Test getting transaction hex data."""
        special_txs = loader.get_special_transactions()
        test_txid = special_txs[0]["txid"]

        hex_data = loader.get_special_transaction_hex(test_txid)
        assert hex_data is not None
        assert isinstance(hex_data, str)
        assert len(hex_data) > 0

    def test_get_test_block_data(self, loader):
        """Test getting test block data."""
        block_data = loader.get_test_block_data()
        assert block_data is not None
        assert "height" in block_data
        assert "hash" in block_data
        assert "hex" in block_data

    def test_get_test_block_hex(self, loader):
        """Test getting test block hex data."""
        block_hex = loader.get_test_block_hex()
        assert block_hex is not None
        assert isinstance(block_hex, str)
        assert len(block_hex) > 0

    def test_create_mock_getrawtransaction(self, loader):
        """Test creating mock getrawtransaction function."""
        mock_fn = loader.create_mock_getrawtransaction()

        # Test with valid transaction
        special_txs = loader.get_special_transactions()
        test_txid = special_txs[0]["txid"]
        hex_data = mock_fn(test_txid)
        assert isinstance(hex_data, str)
        assert len(hex_data) > 0

        # Test with invalid transaction
        with pytest.raises(Exception):
            mock_fn("invalid_txid")

    def test_create_mock_rpc(self, loader):
        """Test creating mock RPC function."""
        mock_rpc = loader.create_mock_rpc()

        # Test getblockcount
        count = mock_rpc("getblockcount", [])
        assert isinstance(count, int)
        assert count > 0

        # Test getblock with raw data
        block_data = loader.get_test_block_data()
        block_hash = block_data["hash"]

        raw_block = mock_rpc("getblock", [block_hash, 0])
        assert isinstance(raw_block, str)
        assert len(raw_block) > 0

        # Test getblock with structured data
        structured_block = mock_rpc("getblock", [block_hash, 1])
        assert isinstance(structured_block, dict)
        assert "hash" in structured_block
        assert "height" in structured_block

        # Test invalid method
        with pytest.raises(Exception):
            mock_rpc("invalid_method", [])

    def test_validate_fixtures(self, loader):
        """Test fixtures validation."""
        is_valid = loader.validate_fixtures()
        assert is_valid is True

    def test_convenience_functions(self):
        """Test convenience functions."""
        # Test get_special_transaction_hex
        special_txs = BitcoinFixturesLoader().get_special_transactions()
        test_txid = special_txs[0]["txid"]

        hex_data = get_special_transaction_hex(test_txid)
        assert hex_data is not None
        assert isinstance(hex_data, str)

        # Test get_test_block_hex
        block_hex = get_test_block_hex()
        assert block_hex is not None
        assert isinstance(block_hex, str)
