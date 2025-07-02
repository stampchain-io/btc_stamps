"""
Test that SRC-721 description field parsing is NOT implemented.
Our implementation does not parse description fields for SRC-721 data.
"""

import pytest

from index_core.models import StampData


class TestSRC721DescriptionParsing:
    """Test that pipe-delimited description field parsing is NOT implemented."""

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
            "block_index": 850000,
            "block_time": 1234567890,
            "is_op_return": False,
            "p2wsh_data": None,
            "prev_tx_hash": "",
            "destination_nvalue": 0,
        }

    def test_parse_mint_description(self, base_stamp_data):
        """Test that mint description is NOT parsed for SRC-721 data."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "STAMP"

        # Simulate Counterparty asset data with mint description
        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": "stamp:721|c:A98765432109876543210|op:mint|id:42",
            "quantity": 1,
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)

        # Verify no parsing occurred
        assert stamp.ident == "STAMP"  # Should remain STAMP
        assert not hasattr(stamp, "recursive_mint_cpid") or stamp.recursive_mint_cpid is None
        assert not hasattr(stamp, "recursive_src721_data") or stamp.recursive_src721_data is None

    def test_parse_deploy_description(self, base_stamp_data):
        """Test that deploy description is NOT parsed for SRC-721 data."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "STAMP"

        # Simulate deploy description
        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": "stamp:721|op:deploy|name:Cool Collection|description:A cool collection|website:https://example.com",
            "quantity": 1,
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)

        # Verify no parsing occurred
        assert stamp.ident == "STAMP"  # Should remain STAMP
        assert stamp.collection_name is None
        assert stamp.collection_description is None
        assert stamp.collection_website is None
        assert stamp.collection_onchain is None
        assert not hasattr(stamp, "recursive_src721_data") or stamp.recursive_src721_data is None

    def test_parse_description_with_spaces(self, base_stamp_data):
        """Test that description with spaces is NOT parsed."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "STAMP"

        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": "stamp:721|op:deploy|name:My Cool Collection|description:This is a very cool collection",
            "quantity": 1,
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)

        assert stamp.ident == "STAMP"  # Should remain STAMP
        assert stamp.collection_name is None
        assert stamp.collection_description is None

    def test_parse_description_case_handling(self, base_stamp_data):
        """Test that case variations are NOT parsed."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "STAMP"

        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": "STAMP:721|C:A98765432109876543210|OP:MINT|ID:42",
            "quantity": 1,
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)

        # No parsing should occur
        assert stamp.ident == "STAMP"  # Should remain STAMP
        assert not hasattr(stamp, "recursive_src721_data") or stamp.recursive_src721_data is None

    def test_parse_invalid_description(self, base_stamp_data):
        """Test that malformed description is NOT parsed."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "STAMP"

        # Missing colons in some parts
        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": "stamp:721|invalid_part|op:mint",
            "quantity": 1,
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)

        # No parsing should occur
        assert stamp.ident == "STAMP"  # Should remain STAMP
        assert not hasattr(stamp, "recursive_src721_data") or stamp.recursive_src721_data is None

    def test_empty_description_parts(self, base_stamp_data):
        """Test that empty description parts are NOT parsed."""
        stamp = StampData(**base_stamp_data)
        stamp.ident = "STAMP"

        cp_asset = {
            "cpid": "A12345678901234567890",
            "description": "stamp:721|op:deploy|name:|description:",
            "quantity": 1,
            "locked": True,
            "divisible": False,
            "message_index": 12345,
        }

        stamp.update_stamp_data_rows_from_cp_asset(cp_asset)

        # No parsing should occur
        assert stamp.ident == "STAMP"  # Should remain STAMP
        assert not hasattr(stamp, "recursive_src721_data") or stamp.recursive_src721_data is None
        assert stamp.collection_name is None
        assert stamp.collection_description is None
