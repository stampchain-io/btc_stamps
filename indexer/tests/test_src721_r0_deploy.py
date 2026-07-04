import base64
import json
import unittest
from unittest.mock import MagicMock, patch

from src.index_core.models import StampData


class TestSRC721R0Deploy(unittest.TestCase):
    """Test cases for SRC-721R (v:r0) deploy detection in P2WSH transactions"""

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

    def test_r0_deploy_detection_basic(self):
        """Test basic r0 deploy detection with minimal data"""
        # Create P2WSH data with r0 deploy - includes p: "SRC-721" as per protocol
        deploy_data = {"p": "SRC-721", "op": "deploy", "v": "r0", "name": "Test Collection"}
        p2wsh_data = json.dumps(deploy_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)

        # Process P2WSH data - this will set ident to SRC-721 via the "p" field
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Verify detection
        self.assertEqual(stamp_data.ident, "SRC-721")
        self.assertEqual(stamp_data.collection_name, "Test Collection")
        self.assertEqual(stamp_data.collection_onchain, 1)
        self.assertIsNone(stamp_data.collection_description)
        self.assertIsNone(stamp_data.collection_website)

    def test_r0_deploy_with_full_metadata(self):
        """Test r0 deploy detection with complete metadata"""
        deploy_data = {
            "p": "SRC-721",
            "op": "deploy",
            "v": "r0",
            "name": "Full Test Collection",
            "description": "A complete test collection",
            "website": "https://example.com",
        }
        p2wsh_data = json.dumps(deploy_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Verify all metadata extracted
        self.assertEqual(stamp_data.ident, "SRC-721")
        self.assertEqual(stamp_data.collection_name, "Full Test Collection")
        self.assertEqual(stamp_data.collection_description, "A complete test collection")
        self.assertEqual(stamp_data.collection_website, "https://example.com")
        self.assertEqual(stamp_data.collection_onchain, 1)

    def test_r0_deploy_case_insensitive(self):
        """Test that version check is case insensitive"""
        for version in ["r0", "R0", "R0", "r0"]:
            deploy_data = {
                "p": "SRC-721",
                "op": "DEPLOY",  # Also test uppercase op
                "v": version,
                "name": f"Test Collection {version}",
            }
            p2wsh_data = json.dumps(deploy_data).encode("utf-8")

            stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
            stamp_data.process_p2wsh_data(self.mock_decode_base64)

            self.assertEqual(stamp_data.ident, "SRC-721", f"Failed for version: {version}")
            self.assertEqual(stamp_data.collection_name, f"Test Collection {version}")

    def test_non_r0_deploy_not_detected(self):
        """Test that non-r0 deploys are not detected"""
        # Test with v1 deploy
        deploy_data = {"p": "SRC-721", "op": "deploy", "v": "v1", "name": "V1 Collection"}
        p2wsh_data = json.dumps(deploy_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be SRC-721 but no collection metadata extracted (not r0)
        self.assertEqual(stamp_data.ident, "SRC-721")
        self.assertIsNone(stamp_data.collection_name)
        self.assertIsNone(stamp_data.collection_onchain)

    def test_r0_mint_not_detected_as_deploy(self):
        """Test that r0 mints are not detected as deploys"""
        mint_data = {"p": "SRC-721", "op": "mint", "v": "r0", "c": "A12345678901234567890"}
        p2wsh_data = json.dumps(mint_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be SRC-721 but no collection metadata (mints don't create collections)
        self.assertEqual(stamp_data.ident, "SRC-721")
        self.assertIsNone(stamp_data.collection_name)

    def test_r0_deploy_without_name(self):
        """Test that r0 deploy without name doesn't mark as onchain"""
        deploy_data = {"p": "SRC-721", "op": "deploy", "v": "r0", "description": "No name collection"}
        p2wsh_data = json.dumps(deploy_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be detected as SRC-721 but not onchain without name
        self.assertEqual(stamp_data.ident, "SRC-721")
        self.assertIsNone(stamp_data.collection_name)
        self.assertIsNone(stamp_data.collection_onchain)

    def test_non_json_p2wsh_not_affected(self):
        """Test that non-JSON P2WSH data is not affected"""
        # HTML content
        p2wsh_data = b"<html><body>Test HTML</body></html>"

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.stamp_mimetype = "text/html"  # Set after initial processing
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should remain as detected by mime type
        self.assertNotEqual(stamp_data.ident, "SRC-721")

    def test_invalid_json_handled_gracefully(self):
        """Test that invalid JSON doesn't crash"""
        p2wsh_data = b'{"invalid": json, no closing'

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should handle gracefully
        self.assertNotEqual(stamp_data.ident, "SRC-721")
        self.assertIsNone(stamp_data.collection_name)

    def test_before_src721_genesis_block(self):
        """Test that r0 deploys before genesis block are not detected"""
        deploy_data = {"p": "SRC-721", "op": "deploy", "v": "r0", "name": "Early Collection"}
        p2wsh_data = json.dumps(deploy_data).encode("utf-8")

        # Set block index before genesis
        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data, block_index=100000)  # Before CP_SRC721_GENESIS_BLOCK
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should not extract collection metadata before genesis block
        self.assertEqual(stamp_data.ident, "SRC-721")  # Still identified as SRC-721 from "p" field
        self.assertIsNone(stamp_data.collection_name)  # But no collection metadata extracted

    def test_numeric_version_handled(self):
        """Test that numeric version 0 is handled correctly"""
        deploy_data = {
            "p": "SRC-721",
            "op": "deploy",
            "v": 0,  # Numeric instead of string
            "name": "Numeric Version Collection",
        }
        p2wsh_data = json.dumps(deploy_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be SRC-721 but not extract metadata (looking for "r0" string, not numeric 0)
        self.assertEqual(stamp_data.ident, "SRC-721")
        self.assertIsNone(stamp_data.collection_name)

    def test_src20_not_changed_to_src721(self):
        """Test that SRC-20 stamps are not changed to SRC-721"""
        # SRC-20 should have p: "SRC-20", not "SRC-721"
        deploy_data = {"p": "SRC-20", "op": "deploy", "v": "r0", "name": "Test Collection"}
        p2wsh_data = json.dumps(deploy_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be identified as SRC-20, not SRC-721
        self.assertEqual(stamp_data.ident, "SRC-20")
        self.assertIsNone(stamp_data.collection_name)  # No collection metadata for SRC-20


if __name__ == "__main__":
    unittest.main()
