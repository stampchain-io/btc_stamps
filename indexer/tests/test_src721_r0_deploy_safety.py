import base64
import json
import unittest
from unittest.mock import MagicMock, patch

from src.index_core.models import StampData


class TestSRC721R0DeploySafety(unittest.TestCase):
    """Test cases to ensure r0 deploy detection doesn't affect other protocols"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_db = MagicMock()
        self.valid_stamps_in_block = []

        # Base stamp data for testing
        self.base_stamp_data = {
            "tx_hash": "test_tx_hash_123",
            "source": "test_source_address",
            "prev_tx_hash": "prev_tx_hash",
            "destination": "test_destination",
            "destination_nvalue": 1000,
            "btc_amount": 0.001,
            "fee": 0.0001,
            "data": "test_data",
            "decoded_tx": {},
            "keyburn": 0,
            "tx_index": 1,
            "block_index": 900000,  # After CP_SRC721_GENESIS_BLOCK
            "block_time": 1234567890,
            "is_op_return": False,
            "p2wsh_data": b"test_p2wsh_data",
            "_lock": MagicMock(),
        }

    def create_stamp_data(self, **kwargs):
        """Create a StampData instance with test data"""
        data = self.base_stamp_data.copy()
        data.update(kwargs)
        return StampData(**data)

    def mock_decode_base64(self, base64_string, block_index):
        """Mock decode_base64 function that returns the decoded data"""
        try:
            decoded = base64.b64decode(base64_string)
            # Try to parse as JSON to set proper mimetype
            try:
                json.loads(decoded.decode("utf-8"))
                # Return the JSON string, not bytes
                return decoded.decode("utf-8"), True
            except:
                return decoded, True
        except:
            return None, False

    def test_src20_with_r0_not_affected(self):
        """Test that SRC-20 with v:r0 is not affected"""
        src20_data = {
            "p": "SRC-20",
            "op": "deploy",
            "v": "r0",  # SRC-20 shouldn't have this, but test anyway
            "tick": "TEST",
            "max": "1000",
            "lim": "10",
            "dec": "0",
        }
        p2wsh_data = json.dumps(src20_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be identified as SRC-20, not changed
        self.assertEqual(stamp_data.ident, "SRC-20")
        self.assertIsNone(stamp_data.collection_name)
        self.assertIsNone(stamp_data.collection_onchain)

    def test_src101_with_r0_not_affected(self):
        """Test that SRC-101 with v:r0 is not affected"""
        src101_data = {
            "p": "SRC-101",
            "op": "deploy",
            "v": "r0",  # SRC-101 shouldn't have this, but test anyway
            "name": "Test NFT",
            "symbol": "TNFT",
        }
        p2wsh_data = json.dumps(src101_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be identified as SRC-101, not changed
        self.assertEqual(stamp_data.ident, "SRC-101")
        self.assertIsNone(stamp_data.collection_name)
        self.assertIsNone(stamp_data.collection_onchain)

    def test_regular_stamp_with_r0_not_affected(self):
        """Test that regular stamps (no p field) with v:r0 are not affected"""
        stamp_data_json = {"op": "deploy", "v": "r0", "name": "Should not be a collection", "data": "Some stamp data"}
        p2wsh_data = json.dumps(stamp_data_json).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should not be SRC-721
        self.assertNotEqual(stamp_data.ident, "SRC-721")
        self.assertIsNone(stamp_data.collection_name)
        self.assertIsNone(stamp_data.collection_onchain)

    def test_src20_mint_not_affected(self):
        """Test that SRC-20 mint operations are not affected"""
        src20_mint = {"p": "SRC-20", "op": "mint", "tick": "TEST", "amt": "100"}
        p2wsh_data = json.dumps(src20_mint).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should remain SRC-20
        self.assertEqual(stamp_data.ident, "SRC-20")
        self.assertIsNone(stamp_data.collection_name)

    def test_src20_transfer_not_affected(self):
        """Test that SRC-20 transfer operations are not affected"""
        src20_transfer = {"p": "SRC-20", "op": "transfer", "tick": "TEST", "amt": "50"}
        p2wsh_data = json.dumps(src20_transfer).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should remain SRC-20
        self.assertEqual(stamp_data.ident, "SRC-20")
        self.assertIsNone(stamp_data.collection_name)

    def test_unknown_protocol_with_r0_not_affected(self):
        """Test that unknown protocols with v:r0 are not affected"""
        unknown_data = {"p": "SRC-999", "op": "deploy", "v": "r0", "name": "Unknown Protocol Test"}  # Unknown protocol
        p2wsh_data = json.dumps(unknown_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be UNKNOWN, not SRC-721
        self.assertEqual(stamp_data.ident, "UNKNOWN")
        self.assertIsNone(stamp_data.collection_name)

    def test_html_p2wsh_not_affected(self):
        """Test that HTML P2WSH content without /s/ references is not affected"""
        html_content = b"""<html>
        <head><title>Test HTML</title></head>
        <body>
            <img src="/images/test.png">
            <script>var v = "r0"; var op = "deploy";</script>
        </body>
        </html>"""

        stamp_data = self.create_stamp_data(p2wsh_data=html_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should not be SRC-721 from HTML content without /s/ reference
        self.assertNotEqual(stamp_data.ident, "SRC-721")
        self.assertIsNone(stamp_data.collection_name)

    def test_svg_p2wsh_not_affected(self):
        """Test that SVG P2WSH content without /s/ references is not affected"""
        svg_content = b"""<svg xmlns="http://www.w3.org/2000/svg">
        <text x="10" y="20">v: r0, op: deploy</text>
        <image href="/images/test.svg"/>
        </svg>"""

        stamp_data = self.create_stamp_data(p2wsh_data=svg_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should not be SRC-721 from SVG content without /s/ reference
        self.assertNotEqual(stamp_data.ident, "SRC-721")
        self.assertIsNone(stamp_data.collection_name)

    def test_malformed_json_with_src721_not_crash(self):
        """Test that malformed JSON with p:SRC-721 doesn't crash"""
        # JSON that starts valid but becomes invalid
        malformed_json = b'{"p": "SRC-721", "op": "deploy", "v": "r0", invalid json here'

        stamp_data = self.create_stamp_data(p2wsh_data=malformed_json)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should handle gracefully without setting collection
        self.assertIsNone(stamp_data.collection_name)

    def test_binary_data_not_affected(self):
        """Test that binary P2WSH data is not affected"""
        # Random binary data
        binary_data = b"\x00\x01\x02\x03\x04\x05\xff\xfe\xfd"

        stamp_data = self.create_stamp_data(p2wsh_data=binary_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should not crash or be identified as SRC-721
        self.assertNotEqual(stamp_data.ident, "SRC-721")
        self.assertIsNone(stamp_data.collection_name)

    def test_nested_json_not_affected(self):
        """Test that nested JSON structures don't cause issues"""
        nested_data = {
            "p": "SRC-721",
            "op": "deploy",
            "v": {"version": "r0", "sub": "data"},  # v is an object instead of string
            "name": "Should not be detected",
        }
        p2wsh_data = json.dumps(nested_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # v is not a string "r0", so no collection
        self.assertEqual(stamp_data.ident, "SRC-721")
        self.assertIsNone(stamp_data.collection_name)

    def test_empty_values_handled(self):
        """Test that empty values are handled properly"""
        empty_data = {
            "p": "SRC-721",
            "op": "deploy",
            "v": "r0",
            "name": "",  # Empty name
            "description": None,  # None value
            "website": "",  # Empty string
        }
        p2wsh_data = json.dumps(empty_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be SRC-721 but not onchain (no name)
        self.assertEqual(stamp_data.ident, "SRC-721")
        self.assertEqual(stamp_data.collection_name, "")  # Empty string
        self.assertIsNone(stamp_data.collection_onchain)  # Not onchain without name

    def test_html_with_s_reference_is_detected(self):
        """Test that HTML with /s/ reference IS detected as SRC-721 (OLGA mint)"""
        html_content = b"""<html>
        <body>
            <img src="/s/A12345678901234567890">
        </body>
        </html>"""

        stamp_data = self.create_stamp_data(p2wsh_data=html_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be detected as SRC-721 OLGA mint
        self.assertEqual(stamp_data.ident, "SRC-721")

    def test_svg_with_s_reference_is_detected(self):
        """Test that SVG with /s/ reference IS detected as SRC-721 (OLGA mint)"""
        svg_content = b"""<svg xmlns="http://www.w3.org/2000/svg">
        <image href="/s/A98765432109876543210"/>
        </svg>"""

        stamp_data = self.create_stamp_data(p2wsh_data=svg_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be detected as SRC-721 OLGA mint
        self.assertEqual(stamp_data.ident, "SRC-721")


if __name__ == "__main__":
    unittest.main()
