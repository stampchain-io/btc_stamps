"""Tests for parser module."""

import unittest
from unittest import mock

from index_core.parser import (
    parse_base64_from_hex,
    parse_base64_from_hex_opreturn,
    parse_file_from_hex,
    parse_opreturn,
)


class TestParser(unittest.TestCase):
    """Test parser functionality."""

    def test_parse_base64_from_hex_valid_stamp(self):
        """Test parsing valid STAMP data from hex."""
        # STAMP:base64data
        hex_data = "5354414d503a54323968633256536233566e5a41" # "STAMP:T29hc2VSb3VnZA"
        result = parse_base64_from_hex(hex_data)
        self.assertEqual(result, b"T29hc2VSb3VnZA")

    def test_parse_base64_from_hex_no_stamp_prefix(self):
        """Test parsing hex without STAMP prefix."""
        hex_data = "48656c6c6f20576f726c64"  # "Hello World"
        result = parse_base64_from_hex(hex_data)
        self.assertIsNone(result)

    def test_parse_base64_from_hex_invalid_hex(self):
        """Test parsing invalid hex data."""
        hex_data = "ZZZZ"  # Invalid hex
        result = parse_base64_from_hex(hex_data)
        self.assertIsNone(result)

    def test_parse_base64_from_hex_opreturn_valid(self):
        """Test parsing valid OP_RETURN STAMP data."""
        # STAMP:base64data
        hex_data = "5354414d503a54323968633256536233566e5a41"
        result = parse_base64_from_hex_opreturn(hex_data)
        self.assertEqual(result, b"T29hc2VSb3VnZA")

    def test_parse_file_from_hex_valid_stamp(self):
        """Test parsing file from hex with STAMP prefix."""
        # STAMP:base64data (base64 decodes to "OaseRougd")
        hex_data = "5354414d503a54323968633256536233566e5a41"
        result = parse_file_from_hex(hex_data)
        self.assertEqual(result, b"OaseRougd")

    def test_parse_file_from_hex_no_stamp(self):
        """Test parsing file from hex without STAMP prefix."""
        hex_data = "48656c6c6f"  # "Hello"
        result = parse_file_from_hex(hex_data)
        self.assertIsNone(result)

    def test_parse_file_from_hex_invalid_base64(self):
        """Test parsing file with invalid base64 after STAMP prefix."""
        # STAMP:!@#$ (invalid base64)
        hex_data = "5354414d503a21402324"
        result = parse_file_from_hex(hex_data)
        self.assertIsNone(result)

    def test_parse_opreturn_with_stamp(self):
        """Test parsing OP_RETURN data containing STAMP."""
        data = "STAMP:T29hc2VSb3VnZA"
        result = parse_opreturn(data)
        self.assertEqual(result, b"OaseRougd")

    def test_parse_opreturn_without_stamp(self):
        """Test parsing OP_RETURN data without STAMP."""
        data = "Hello World"
        result = parse_opreturn(data)
        self.assertIsNone(result)

    def test_parse_opreturn_empty(self):
        """Test parsing empty OP_RETURN data."""
        data = ""
        result = parse_opreturn(data)
        self.assertIsNone(result)

    @mock.patch("index_core.parser.base64.b64decode")
    def test_parse_opreturn_base64_error(self, mock_b64decode):
        """Test parse_opreturn handles base64 decode errors."""
        mock_b64decode.side_effect = Exception("Invalid base64")
        data = "STAMP:InvalidBase64"
        result = parse_opreturn(data)
        self.assertIsNone(result)

    def test_parse_base64_from_hex_with_rust_decoding_error(self):
        """Test parse_base64_from_hex handles rust decoding errors."""
        # Since we can't easily mock the rust module, we test with invalid input
        hex_data = None  # This should cause an error
        result = parse_base64_from_hex(hex_data)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()