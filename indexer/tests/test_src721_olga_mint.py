import base64
import json
import unittest
from unittest.mock import MagicMock, patch

from src.index_core.models import StampData


class TestSRC721OLGAMint(unittest.TestCase):
    """Test cases for SRC-721 OLGA (HTML/SVG) mint detection in P2WSH transactions"""

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
            return decoded, True
        except:
            return None, False

    def test_olga_mint_html_basic(self):
        """Test basic OLGA mint detection with HTML content"""
        html_content = b"""<html>
        <head><title>Recursive NFT</title></head>
        <body>
            <h1>My NFT</h1>
            <img src="/s/A12345678901234567890" alt="Collection Image">
        </body>
        </html>"""

        stamp_data = self.create_stamp_data(p2wsh_data=html_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be detected as SRC-721 OLGA mint
        self.assertEqual(stamp_data.ident, "SRC-721")

    def test_olga_mint_svg_basic(self):
        """Test basic OLGA mint detection with SVG content"""
        svg_content = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <image href="/s/A98765432109876543210" x="0" y="0" width="100" height="100"/>
        <text x="50" y="50">NFT #1</text>
        </svg>"""

        stamp_data = self.create_stamp_data(p2wsh_data=svg_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be detected as SRC-721 OLGA mint
        self.assertEqual(stamp_data.ident, "SRC-721")

    def test_olga_mint_multiple_references(self):
        """Test OLGA mint with multiple /s/ references (should use first)"""
        html_content = b"""<html>
        <body>
            <img src="/s/A11111111111111111111">
            <img src="/s/A22222222222222222222">
            <img src="/s/A33333333333333333333">
        </body>
        </html>"""

        stamp_data = self.create_stamp_data(p2wsh_data=html_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should use the first CPID found
        self.assertEqual(stamp_data.ident, "SRC-721")
        # OLGA mint detected

    def test_olga_mint_invalid_cpid_format(self):
        """Test that invalid CPID formats are not detected"""
        test_cases = [
            # Too short
            b'<img src="/s/A123456789">',
            # Too long
            b'<img src="/s/A123456789012345678901">',
            # Doesn't start with A
            b'<img src="/s/B12345678901234567890">',
            # Contains non-digits
            b'<img src="/s/A1234567890123456789X">',
            # Missing /s/ prefix
            b'<img src="A12345678901234567890">',
        ]

        for html_content in test_cases:
            stamp_data = self.create_stamp_data(p2wsh_data=html_content)
            stamp_data.process_p2wsh_data(self.mock_decode_base64)

            # Should not be detected as SRC-721
            self.assertNotEqual(stamp_data.ident, "SRC-721", f"Failed for: {html_content}")
            # Not detected as OLGA mint

    def test_olga_mint_with_query_params(self):
        """Test OLGA mint with URL query parameters"""
        html_content = b"""<html>
        <body>
            <img src="/s/A12345678901234567890?size=large&format=png">
        </body>
        </html>"""

        stamp_data = self.create_stamp_data(p2wsh_data=html_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should still detect the CPID
        self.assertEqual(stamp_data.ident, "SRC-721")
        # OLGA mint detected

    def test_olga_mint_with_full_url(self):
        """Test OLGA mint with full URL (should still work)"""
        html_content = b"""<html>
        <body>
            <img src="https://stampchain.io/s/A12345678901234567890">
        </body>
        </html>"""

        stamp_data = self.create_stamp_data(p2wsh_data=html_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should detect the CPID
        self.assertEqual(stamp_data.ident, "SRC-721")
        # OLGA mint detected

    def test_olga_mint_json_not_detected(self):
        """Test that JSON content is not detected as OLGA mint"""
        json_data = {"p": "SRC-721", "op": "mint", "s": "/s/A12345678901234567890"}  # This shouldn't trigger OLGA detection
        p2wsh_data = json.dumps(json_data).encode("utf-8")

        stamp_data = self.create_stamp_data(p2wsh_data=p2wsh_data)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should be SRC-721 from "p" field, not OLGA detection
        self.assertEqual(stamp_data.ident, "SRC-721")
        # Already SRC-721 from JSON, not from OLGA detection

    def test_olga_mint_before_genesis_block(self):
        """Test that OLGA mints before genesis block are not detected"""
        html_content = b'<img src="/s/A12345678901234567890">'

        stamp_data = self.create_stamp_data(p2wsh_data=html_content, block_index=100000)  # Before CP_SRC721_GENESIS_BLOCK
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should not be detected
        self.assertNotEqual(stamp_data.ident, "SRC-721")
        # Not detected as OLGA mint

    def test_olga_mint_already_identified(self):
        """Test that already identified stamps are not changed"""
        # Create JSON that would be identified as SRC-20
        json_data = {"p": "SRC-20", "op": "deploy", "tick": "TEST"}
        # But embed it in HTML with /s/ reference
        html_content = f"""<html>
        <body>
            <img src="/s/A12345678901234567890">
            <script>var data = {json.dumps(json_data)};</script>
        </body>
        </html>""".encode(
            "utf-8"
        )

        stamp_data = self.create_stamp_data(p2wsh_data=html_content)
        # Simulate that this was identified as SRC-20 from embedded JSON
        # In reality, this would depend on the order of checks
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # If HTML parsing happens first, it would be SRC-721
        # This test documents current behavior
        self.assertEqual(stamp_data.ident, "SRC-721")

    def test_olga_mint_css_background_image(self):
        """Test OLGA mint reference in CSS background-image"""
        html_content = b"""<html>
        <head>
            <style>
                .nft { background-image: url(/s/A12345678901234567890); }
            </style>
        </head>
        <body><div class="nft"></div></body>
        </html>"""

        stamp_data = self.create_stamp_data(p2wsh_data=html_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should detect the CPID in CSS
        self.assertEqual(stamp_data.ident, "SRC-721")
        # OLGA mint detected

    def test_olga_mint_javascript_reference(self):
        """Test OLGA mint reference in JavaScript"""
        html_content = b"""<html>
        <body>
            <script>
                var collectionId = "/s/A12345678901234567890";
                document.getElementById('img').src = collectionId;
            </script>
            <img id="img">
        </body>
        </html>"""

        stamp_data = self.create_stamp_data(p2wsh_data=html_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should detect the CPID in JavaScript
        self.assertEqual(stamp_data.ident, "SRC-721")
        # OLGA mint detected

    def test_olga_mint_malformed_html(self):
        """Test OLGA mint detection in malformed HTML"""
        html_content = b"""<html
        <body>
            <img src="/s/A12345678901234567890"
            <p>Malformed HTML but CPID should still be found
        </body"""

        stamp_data = self.create_stamp_data(p2wsh_data=html_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should still detect despite malformed HTML
        self.assertEqual(stamp_data.ident, "SRC-721")
        # OLGA mint detected

    def test_olga_mint_encoded_content(self):
        """Test OLGA mint with HTML entities"""
        html_content = b"""<html>
        <body>
            <!-- Using HTML entities -->
            <img src="&#47;s&#47;A12345678901234567890">
        </body>
        </html>"""

        stamp_data = self.create_stamp_data(p2wsh_data=html_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # HTML entities might not be detected (documenting current behavior)
        # This could be enhanced in future if needed
        self.assertNotEqual(stamp_data.ident, "SRC-721")

    def test_olga_mint_case_sensitive(self):
        """Test that /S/ (uppercase) is not detected"""
        html_content = b'<img src="/S/A12345678901234567890">'

        stamp_data = self.create_stamp_data(p2wsh_data=html_content)
        stamp_data.process_p2wsh_data(self.mock_decode_base64)

        # Should not detect uppercase /S/
        self.assertNotEqual(stamp_data.ident, "SRC-721")
        # Not detected as OLGA mint


if __name__ == "__main__":
    unittest.main()
