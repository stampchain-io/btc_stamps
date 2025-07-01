"""
Test SRC-721 detection from Counterparty description field.
Tests both regular stamps and P2WSH stamps with stamp:721 pattern.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

# Set test environment variables BEFORE importing any indexer modules
os.environ["USE_TEST_DB"] = "1"
os.environ["MOCK_DB"] = "1"
os.environ["TESTING"] = "1"

from index_core.models import StampData


class TestSRC721DescriptionDetection:
    """Test SRC-721 detection from description field patterns."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database for testing."""
        db = MagicMock()
        db.query_one.return_value = None
        db.cursor.return_value.__enter__.return_value = MagicMock()
        return db

    @pytest.fixture
    def base_stamp_data(self):
        """Base stamp data for testing."""
        return {
            "tx_hash": "test_tx_hash",
            "source": "test_source",
            "destination": "test_dest",
            "btc_amount": 0,
            "fee": 0,
            "data": "test_data",
            "decoded_tx": "{}",
            "keyburn": 1,
            "tx_index": 0,
            "block_index": 850000,  # After SRC-721 genesis
            "block_time": 1234567890,
            "is_op_return": False,
            "p2wsh_data": None,
            "prev_tx_hash": "",
            "destination_nvalue": 0,
        }

    def test_stamp_721_description_basic(self, base_stamp_data):
        """Test basic stamp:721 pattern detection."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "STAMP"

        # Simulate Counterparty asset data with stamp:721 description
        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": "stamp:721|c:A98765432109876543210|op:mint|id:1",
            "quantity": 1,
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        # Process the stamp
        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)

        # Verify it changed from STAMP to SRC-721
        assert stamp.ident == "SRC-721"

    def test_stamp_721_case_insensitive(self, base_stamp_data):
        """Test case insensitive detection of STAMP:721."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "STAMP"

        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": "STAMP:721|c:A98765432109876543210|op:mint|id:2",
            "quantity": 1,
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)
        assert stamp.ident == "SRC-721"

    def test_stamp_721_not_at_beginning(self, base_stamp_data):
        """Test that stamp:721 not at beginning doesn't trigger."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "STAMP"

        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": "This has stamp:721 in the middle",
            "quantity": 1,
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)
        # Should remain STAMP
        assert stamp.ident == "STAMP"

    def test_src20_not_changed(self, base_stamp_data):
        """Test that SRC-20 stamps are not changed even with stamp:721 description."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "SRC-20"
        stamp.src20_dict = {"p": "src-20", "op": "mint", "tick": "TEST", "amt": "100"}

        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": "stamp:721|c:A98765432109876543210|op:mint|id:1",
            "quantity": 0,  # SRC-20 has 0 quantity
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)
        # Should remain SRC-20
        assert stamp.ident == "SRC-20"

    def test_src101_not_changed(self, base_stamp_data):
        """Test that SRC-101 stamps are not changed."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "SRC-101"

        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": "stamp:721|c:A98765432109876543210|op:mint|id:1",
            "quantity": 1,
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)
        # Should remain SRC-101
        assert stamp.ident == "SRC-101"

    def test_empty_description(self, base_stamp_data):
        """Test that empty description doesn't cause issues."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "STAMP"

        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": "",
            "quantity": 1,
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)
        # Should remain STAMP
        assert stamp.ident == "STAMP"

    def test_none_description(self, base_stamp_data):
        """Test that None description doesn't cause issues."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "STAMP"

        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": None,
            "quantity": 1,
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)
        # Should remain STAMP
        assert stamp.ident == "STAMP"

    @patch("index_core.models.logger")
    def test_p2wsh_src721_preserves_content(self, mock_logger, base_stamp_data, mock_db):
        """Test that P2WSH SRC-721 stamps preserve their HTML/SVG content."""
        # Create stamp with P2WSH data
        base_stamp_data["p2wsh_data"] = b"<html><body>Test HTML content</body></html>"
        stamp = StampData(**base_stamp_data)
        stamp.ident = "SRC-721"
        stamp.stamp_mimetype = "text/html"
        stamp.decoded_base64 = "<html><body>Test HTML content</body></html>"
        stamp.supply = 1

        # Mock the _lock attribute
        stamp._lock = MagicMock()

        # Process as SRC-721
        stamp.process_src721([], mock_db)

        # Verify the content was preserved
        assert stamp.decoded_base64 == "<html><body>Test HTML content</body></html>"
        assert stamp.stamp_mimetype == "text/html"
        assert stamp.src_data == ""  # Should be empty for P2WSH SRC-721
        # Check that we logged preservation
        mock_logger.debug.assert_called_with(f"Preserving P2WSH HTML/SVG content for SRC-721 stamp {stamp.tx_hash}")

    @patch("index_core.models.validate_src721_and_process")
    def test_non_p2wsh_src721_processes_normally(self, mock_validate, base_stamp_data, mock_db):
        """Test that non-P2WSH SRC-721 stamps go through normal processing."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "SRC-721"
        stamp.decoded_base64 = {"p": "src-721", "op": "mint", "ts": [1, 2, 3]}
        stamp.supply = 1
        stamp._lock = MagicMock()

        # Mock the validation function
        mock_validate.return_value = (
            "<svg>...</svg>",  # svg_output
            "svg",  # file_suffix
            "Test Collection",  # collection_name
            "Test Description",  # collection_description
            "https://test.com",  # collection_website
            1,  # collection_onchain
        )

        # Process as SRC-721
        stamp.process_src721([], mock_db)

        # Verify normal processing occurred
        assert stamp.decoded_base64 == "<svg>...</svg>"
        assert stamp.file_suffix == "svg"
        assert stamp.stamp_mimetype == "image/svg+xml"
        mock_validate.assert_called_once()

    def test_valid_src721_with_p2wsh(self, base_stamp_data):
        """Test valid_src721 returns True for P2WSH stamps with SRC-721 ident."""
        from config import CP_P2WSH_FEAT_BLOCK_START, CP_SRC721_GENESIS_BLOCK

        base_stamp_data["block_index"] = max(CP_P2WSH_FEAT_BLOCK_START, CP_SRC721_GENESIS_BLOCK) + 1000
        base_stamp_data["p2wsh_data"] = b"<html>test</html>"

        stamp = StampData(**base_stamp_data)
        stamp.ident = "SRC-721"
        stamp.supply = 1
        stamp.keyburn = 0  # P2WSH doesn't require keyburn

        assert stamp.valid_src721() is True

    def test_valid_src721_with_keyburn(self, base_stamp_data):
        """Test valid_src721 returns True for keyburn stamps with SRC-721 ident."""
        from config import CP_SRC721_GENESIS_BLOCK

        base_stamp_data["block_index"] = CP_SRC721_GENESIS_BLOCK + 1000

        stamp = StampData(**base_stamp_data)
        stamp.ident = "SRC-721"
        stamp.supply = 1
        stamp.keyburn = 1

        assert stamp.valid_src721() is True


class TestSRC721DescriptionIntegration:
    """Integration tests with fixtures for known stamp:721 patterns."""

    @pytest.fixture
    def stamp_721_fixtures(self):
        """Fixture data for known stamp:721 patterns from production."""
        return [
            {
                "tx_hash": "example_tx_1",
                "cpid": "A12345678901234567890",
                "description": "stamp:721|c:A98765432109876543210|op:mint|id:42",
                "expected_ident": "SRC-721",
                "has_p2wsh": True,
                "p2wsh_content": "<html><head><script src='/s/A98765432109876543210'></script></head></html>",
            },
            {
                "tx_hash": "example_tx_2",
                "cpid": "A23456789012345678901",
                "description": "stamp:721|c:A87654321098765432109|op:mint|id:100",
                "expected_ident": "SRC-721",
                "has_p2wsh": True,
                "p2wsh_content": "<svg><use href='/s/A87654321098765432109#main'></use></svg>",
            },
            {
                "tx_hash": "example_tx_3",
                "cpid": "A34567890123456789012",
                "description": "Regular stamp description",
                "expected_ident": "STAMP",
                "has_p2wsh": True,
                "p2wsh_content": "<html>Regular HTML content</html>",
            },
        ]

    def test_fixtures_processing(self, stamp_721_fixtures):
        """Test processing of fixture data."""
        for fixture in stamp_721_fixtures:
            stamp_data = {
                "tx_hash": fixture["tx_hash"],
                "source": "test_source",
                "destination": "test_dest",
                "btc_amount": 0,
                "fee": 0,
                "data": "test_data",
                "decoded_tx": "{}",
                "keyburn": 0 if fixture["has_p2wsh"] else 1,
                "tx_index": 0,
                "block_index": 850000,
                "block_time": 1234567890,
                "is_op_return": False,
                "p2wsh_data": fixture["p2wsh_content"].encode() if fixture["has_p2wsh"] else None,
                "prev_tx_hash": "",
                "destination_nvalue": 0,
            }

            stamp = StampData(**stamp_data)
            stamp.ident = "STAMP"

            # Simulate Counterparty asset data
            cp_asset = {
                "cpid": fixture["cpid"],
                "description": fixture["description"],
                "quantity": 1,
                "locked": True,
                "divisible": False,
                "message_index": 12345,
            }

            # Process the stamp
            stamp.update_stamp_data_rows_from_cp_asset(cp_asset)

            # Verify the result
            assert stamp.ident == fixture["expected_ident"], (
                f"Failed for {fixture['tx_hash']}: " f"expected {fixture['expected_ident']}, got {stamp.ident}"
            )


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
