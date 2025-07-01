"""
Test parsing of SRC-721 description field for recursive stamps.
"""

import pytest

from index_core.models import StampData


class TestSRC721DescriptionParsing:
    """Test parsing of pipe-delimited description field."""

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
        """Test parsing mint description."""
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

        # Verify parsing
        assert stamp.ident == "SRC-721"
        assert stamp.recursive_mint_cpid == "A98765432109876543210"
        assert stamp.recursive_src721_data == {"c": "A98765432109876543210", "op": "mint", "id": "42"}

    def test_parse_deploy_description(self, base_stamp_data):
        """Test parsing deploy description."""
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

        # Verify parsing
        assert stamp.ident == "SRC-721"
        assert stamp.collection_name == "Cool Collection"
        assert stamp.collection_description == "A cool collection"
        assert stamp.collection_website == "https://example.com"
        assert stamp.collection_onchain == 1
        assert stamp.recursive_src721_data == {
            "op": "deploy",
            "name": "Cool Collection",
            "description": "A cool collection",
            "website": "https://example.com",
        }

    def test_parse_description_with_spaces(self, base_stamp_data):
        """Test parsing description with spaces in values."""
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

        assert stamp.collection_name == "My Cool Collection"
        assert stamp.collection_description == "This is a very cool collection"

    def test_parse_description_case_handling(self, base_stamp_data):
        """Test that keys are normalized to lowercase."""
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

        # Keys should be lowercase in parsed data
        assert stamp.recursive_src721_data == {"c": "A98765432109876543210", "op": "MINT", "id": "42"}  # Values preserve case

    def test_parse_invalid_description(self, base_stamp_data):
        """Test handling of malformed description."""
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

        # Should still parse valid parts
        assert stamp.ident == "SRC-721"
        assert stamp.recursive_src721_data == {"op": "mint"}

    def test_empty_description_parts(self, base_stamp_data):
        """Test handling of empty values in description."""
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

        # Empty values should be preserved
        assert stamp.recursive_src721_data == {"op": "deploy", "name": "", "description": ""}
        # But collection fields should not be set from empty values
        assert stamp.collection_name is None
        assert stamp.collection_description is None
