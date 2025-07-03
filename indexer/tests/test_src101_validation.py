"""Test SRC-101 transaction validation to ensure proper detection."""

import json

import pytest

from index_core.src101 import check_src101_inputs


class TestSRC101Validation:
    """Test suite for SRC-101 validation."""

    @pytest.fixture
    def mock_data_src101(self):
        """Create a mock SRC-101 transaction data."""
        return {
            "tx_hash": "77fb147b8a5cf5c3c7e5e7b8c7e5e7b8c7e5e7b8c7e5e7b8c7e5e7b8c7e5e7b8",
            "tx_index": 1,
            "block_index": 875000,
            "source": "1AddressWithSRC101Tokens",
            "destination": None,
            "btc_amount": 0,
            "data": json.dumps(
                {
                    "p": "src-101",
                    "op": "deploy",
                    "name": "Test Token",
                    "tick": "TEST",
                    "root": "test-root",
                    "lim": 1000,
                    "owner": "1AddressWithSRC101Tokens",
                    "rec": "record",
                    "pri": 1,
                    "desc": "Test token description",
                    "mintstart": 875000,
                    "mintend": 900000,
                    "wla": "whitelist",
                    "imglp": "imgloop",
                    "imgf": "imgformat",
                    "idua": 100,
                }
            ),
        }

    @pytest.fixture
    def mock_data_src101_mint(self):
        """Create a mock SRC-101 mint transaction data."""
        return {
            "tx_hash": "88fb147b8a5cf5c3c7e5e7b8c7e5e7b8c7e5e7b8c7e5e7b8c7e5e7b8c7e5e7b8",
            "tx_index": 2,
            "block_index": 875001,
            "source": "1MinterAddress",
            "destination": None,
            "btc_amount": 0,
            "data": json.dumps(
                {
                    "p": "src-101",
                    "op": "mint",
                    "hash": "77fb147b8a5cf5c3c7e5e7b8c7e5e7b8c7e5e7b8c7e5e7b8c7e5e7b8c7e5e7b8",
                    "toaddress": "1RecipientAddress",
                    "tokenid": "1",
                    "dua": 100,
                    "prim": "primary",
                    "sig": "signature",
                    "img": "https://example.com/image.png",
                    "coef": 1,
                }
            ),
        }

    @pytest.fixture
    def mock_data_stamp_with_s_pattern(self):
        """Create a mock STAMP transaction with /s/ pattern that should not be SRC-101."""
        return {
            "tx_hash": "99fb147b8a5cf5c3c7e5e7b8c7e5e7b8c7e5e7b8c7e5e7b8c7e5e7b8c7e5e7b8",
            "tx_index": 3,
            "block_index": 875002,
            "source": "1StampAddress",
            "destination": None,
            "btc_amount": 0,
            "data": '<html><body><img src="/s/A12345"></body></html>',
        }

    def test_src101_deploy_detection(self, mock_data_src101):
        """Test that SRC-101 deploy transactions are properly detected."""
        # Decode the data
        decoded_data = json.loads(mock_data_src101["data"])

        # Check SRC-101 inputs
        src101_dict = check_src101_inputs(decoded_data, mock_data_src101["tx_hash"], mock_data_src101["block_index"])

        # Verify it was detected as SRC-101
        assert src101_dict is not None
        assert src101_dict["p"] == "src-101"
        assert src101_dict["op"] == "deploy"
        assert src101_dict["tick"] == "TEST"

    def test_src101_mint_detection(self, mock_data_src101_mint):
        """Test that SRC-101 mint transactions are properly detected."""
        # Decode the data
        decoded_data = json.loads(mock_data_src101_mint["data"])

        # Check SRC-101 inputs
        src101_dict = check_src101_inputs(decoded_data, mock_data_src101_mint["tx_hash"], mock_data_src101_mint["block_index"])

        # Verify it was detected as SRC-101
        assert src101_dict is not None
        assert src101_dict["p"] == "src-101"
        assert src101_dict["op"] == "mint"
        assert src101_dict["tokenid"] == "1"

    def test_stamp_not_misclassified_as_src101(self, mock_data_stamp_with_s_pattern):
        """Test that regular STAMPs with /s/ patterns are not misclassified as SRC-101."""
        # This is HTML content, not JSON
        html_data = mock_data_stamp_with_s_pattern["data"]

        # Check SRC-101 inputs - should return None for non-JSON data
        src101_dict = check_src101_inputs(
            html_data, mock_data_stamp_with_s_pattern["tx_hash"], mock_data_stamp_with_s_pattern["block_index"]
        )

        # Verify it was NOT detected as SRC-101
        assert src101_dict is None

    def test_src101_protocol_identification(self, mock_data_src101):
        """Test that SRC-101 protocol is properly identified in processing."""
        # Decode the data
        decoded_data = json.loads(mock_data_src101["data"])

        # Check SRC-101 inputs
        src101_dict = check_src101_inputs(decoded_data, mock_data_src101["tx_hash"], mock_data_src101["block_index"])

        # Verify it was properly detected
        assert src101_dict is not None
        assert src101_dict["p"] == "src-101"

    def test_src101_not_affected_by_recursive_detection(self):
        """Test that SRC-101 is not affected by recursive SRC-721 detection."""
        # Create SRC-101 data
        src101_data = {
            "p": "src-101",
            "op": "deploy",
            "name": "Test Token",
            "tick": "TEST",
            "root": "test-root",
            "lim": 1000,
            "owner": "1TestAddress",
            "rec": "record",
            "pri": 1,
            "desc": "Test token",
            "mintstart": 875000,
            "mintend": 900000,
            "wla": "whitelist",
            "imglp": "imgloop",
            "imgf": "imgformat",
            "idua": 100,
        }

        # Check it's detected as SRC-101
        src101_dict = check_src101_inputs(src101_data, "test_hash", 875000)

        # Verify it was detected as SRC-101
        assert src101_dict is not None
        assert src101_dict["p"] == "src-101"

    def test_src101_json_validation(self):
        """Test that SRC-101 requires valid JSON format."""
        invalid_inputs = [
            "not json",
            "<html>test</html>",
            '{"p": "not-src-101"}',
            '{"op": "deploy"}',  # Missing protocol
            None,
            "",
            123,
            [],
        ]

        for invalid_input in invalid_inputs:
            src101_dict = check_src101_inputs(invalid_input, "test_hash", 875000)
            assert src101_dict is None, f"Should reject invalid input: {invalid_input}"

    def test_src101_case_insensitive_protocol(self):
        """Test that SRC-101 protocol detection is case-insensitive."""
        variations = ["src-101", "src-101", "Src-101", "sRc-101"]

        for protocol_variant in variations:
            data = {
                "p": protocol_variant,
                "op": "deploy",
                "name": "Test",
                "tick": "TEST",
                "root": "test-root",
                "lim": 1000,
                "owner": "1TestAddress",
                "rec": "record",
                "pri": 1,
                "desc": "Test",
                "mintstart": 875000,
                "mintend": 900000,
                "wla": "whitelist",
                "imglp": "imgloop",
                "imgf": "imgformat",
                "idua": 100,
            }

            src101_dict = check_src101_inputs(data, "test_hash", 875000)
            assert src101_dict is not None
            assert src101_dict["p"].lower() == "src-101"  # Check lowercase
