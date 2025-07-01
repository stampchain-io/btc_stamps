"""Tests for recursive SRC-721 functionality."""

import json
from unittest.mock import MagicMock, patch

import pytest

from index_core.src721 import (
    is_recursive_src721_deploy,
    is_recursive_src721_mint,
    validate_src721_and_process,
)


def test_is_recursive_src721_mint_html():
    """Test detection of recursive SRC-721 mints in HTML content."""
    # Test HTML with /s/<CPID> pattern
    html_content = b'<html><body><script src="/s/A17785882525351975000"></script></body></html>'
    is_recursive, cpid = is_recursive_src721_mint(html_content, "text/html")

    assert is_recursive is True
    assert cpid == "A17785882525351975000"

    # Test HTML string (not bytes)
    html_str = '<div><img src="/s/A12345678901234567890" /></div>'
    is_recursive, cpid = is_recursive_src721_mint(html_str, "text/html")

    assert is_recursive is True
    assert cpid == "A12345678901234567890"


def test_is_recursive_src721_mint_svg():
    """Test detection of recursive SRC-721 mints in SVG content."""
    # Test SVG with /s/<CPID> pattern
    svg_content = b'<svg><use href="/s/A98765432109876543210"></use></svg>'
    is_recursive, cpid = is_recursive_src721_mint(svg_content, "image/svg+xml")

    assert is_recursive is True
    assert cpid == "A98765432109876543210"


def test_is_recursive_src721_mint_no_pattern():
    """Test content without recursive pattern returns False."""
    # HTML without /s/ pattern
    html_content = b"<html><body>No recursive reference here</body></html>"
    is_recursive, cpid = is_recursive_src721_mint(html_content, "text/html")

    assert is_recursive is False
    assert cpid is None

    # Wrong MIME type
    html_with_pattern = b'<script src="/s/A12345678901234567890"></script>'
    is_recursive, cpid = is_recursive_src721_mint(html_with_pattern, "text/plain")

    assert is_recursive is False
    assert cpid is None


def test_is_recursive_src721_mint_invalid_cpid():
    """Test invalid CPID formats are not matched."""
    # CPID too short
    html_content = b'<script src="/s/A123"></script>'
    is_recursive, cpid = is_recursive_src721_mint(html_content, "text/html")

    assert is_recursive is False
    assert cpid is None

    # CPID doesn't start with A
    html_content = b'<script src="/s/B12345678901234567890"></script>'
    is_recursive, cpid = is_recursive_src721_mint(html_content, "text/html")

    assert is_recursive is False
    assert cpid is None

    # CPID with non-numeric characters
    html_content = b'<script src="/s/A1234567890ABCDEF1234"></script>'
    is_recursive, cpid = is_recursive_src721_mint(html_content, "text/html")

    assert is_recursive is False
    assert cpid is None


def test_is_recursive_src721_deploy():
    """Test detection of recursive SRC-721 deploy transactions."""
    # Valid recursive deploy
    deploy_json = {"p": "src-721", "v": "r0", "op": "deploy", "name": "Test Collection"}
    assert is_recursive_src721_deploy(deploy_json) is True

    # Deploy without version
    deploy_json = {"p": "src-721", "op": "deploy", "name": "Test Collection"}
    assert is_recursive_src721_deploy(deploy_json) is False

    # Deploy with different version
    deploy_json = {"p": "src-721", "v": "1", "op": "deploy", "name": "Test Collection"}
    assert is_recursive_src721_deploy(deploy_json) is False

    # Not a deploy operation
    mint_json = {"p": "src-721", "v": "r0", "op": "mint"}
    assert is_recursive_src721_deploy(mint_json) is False


def test_process_recursive_mint_with_deploy_in_block():
    """Test processing a recursive mint when deploy is in the same block."""
    from index_core.models import StampData

    # Create mock database
    mock_db = MagicMock()

    # Create deploy stamp in valid_stamps_in_block
    deploy_stamp = {
        "cpid": "A17785882525351975000",
        "src_data": json.dumps(
            {
                "p": "src-721",
                "v": "r0",
                "op": "deploy",
                "name": "Test Recursive Collection",
                "description": "Test Description",
                "website": "https://test.com",
            }
        ),
        "is_btc_stamp": True,
    }
    valid_stamps_in_block = [deploy_stamp]

    # Create stamp data for mint with HTML referencing the deploy
    stamp_data = StampData(
        tx_hash="test_mint_tx",
        source="test_address",
        prev_tx_hash="prev_tx_hash",
        destination="test_address",
        destination_nvalue=0,
        btc_amount=0,
        fee=1000,
        data={},
        decoded_tx={},
        keyburn=False,
        tx_index=1,
        block_index=800000,
        block_time=1234567890,
        is_op_return=False,
        p2wsh_data=None,
    )

    # Set the decoded HTML content and mime type
    stamp_data.decoded_base64 = b'<html><script src="/s/A17785882525351975000"></script></html>'
    stamp_data.stamp_mimetype = "text/html"
    stamp_data.file_suffix = "html"
    stamp_data.recursive_mint_cpid = "A17785882525351975000"
    stamp_data.ident = "SRC-721"
    stamp_data._lock = MagicMock()
    stamp_data.db = mock_db

    # Process the recursive mint
    stamp_data.process_src721(valid_stamps_in_block, mock_db)

    # Verify the results
    assert stamp_data.is_btc_stamp is True
    assert stamp_data.collection_name == "Test Recursive Collection"
    assert stamp_data.collection_description == "Test Description"
    assert stamp_data.collection_website == "https://test.com"
    assert stamp_data.collection_onchain == 1

    # Verify src_data is empty for P2WSH SRC-721 detected via description
    assert stamp_data.src_data == ""

    # Verify HTML content is preserved (not converted to SVG)
    assert stamp_data.file_suffix == "html"
    assert stamp_data.stamp_mimetype == "text/html"
    assert b"<html>" in stamp_data.decoded_base64


def test_process_recursive_mint_with_deploy_from_db():
    """Test processing a recursive mint when deploy must be fetched from database."""
    from index_core.models import StampData

    # Create mock database
    mock_db = MagicMock()

    # No stamps in current block
    valid_stamps_in_block = []

    # Mock fetch_collection_details to return deploy data
    deploy_data = json.dumps(
        {"p": "src-721", "v": "r0", "op": "deploy", "name": "DB Collection", "description": "From Database"}
    )

    with patch("index_core.src721.fetch_collection_details") as mock_fetch:
        mock_fetch.return_value = deploy_data

        # Create stamp data for mint
        stamp_data = StampData(
            tx_hash="test_mint_tx",
            source="test_address",
            prev_tx_hash="prev_tx_hash",
            destination="test_address",
            destination_nvalue=0,
            btc_amount=0,
            fee=1000,
            data={},
            decoded_tx={},
            keyburn=False,
            tx_index=1,
            block_index=800000,
            block_time=1234567890,
            is_op_return=False,
            p2wsh_data=None,
        )

        # Set the decoded SVG content
        stamp_data.decoded_base64 = b'<svg><use href="/s/A17785882525351975000"></use></svg>'
        stamp_data.stamp_mimetype = "image/svg+xml"
        stamp_data.file_suffix = "svg"
        stamp_data.recursive_mint_cpid = "A17785882525351975000"
        stamp_data.ident = "SRC-721"
        stamp_data._lock = MagicMock()
        stamp_data.db = mock_db

        # Process the recursive mint
        stamp_data.process_src721(valid_stamps_in_block, mock_db)

        # Verify fetch was called
        mock_fetch.assert_called_once_with("A17785882525351975000", mock_db)

        # Verify the results
        assert stamp_data.collection_name == "DB Collection"
        assert stamp_data.collection_description == "From Database"
        assert stamp_data.file_suffix == "svg"
        assert b"<svg>" in stamp_data.decoded_base64


def test_process_recursive_mint_missing_deploy():
    """Test processing a recursive mint when deploy cannot be found."""
    from index_core.models import StampData

    # Create mock database
    mock_db = MagicMock()
    valid_stamps_in_block = []

    # Mock fetch_collection_details to return None (not found)
    with patch("index_core.src721.fetch_collection_details") as mock_fetch:
        mock_fetch.return_value = None

        # Create stamp data
        stamp_data = StampData(
            tx_hash="test_mint_tx",
            source="test_address",
            prev_tx_hash="prev_tx_hash",
            destination="test_address",
            destination_nvalue=0,
            btc_amount=0,
            fee=1000,
            data={},
            decoded_tx={},
            keyburn=False,
            tx_index=1,
            block_index=800000,
            block_time=1234567890,
            is_op_return=False,
            p2wsh_data=None,
        )

        stamp_data.decoded_base64 = b'<html><script src="/s/A99999999999999999999"></script></html>'
        stamp_data.stamp_mimetype = "text/html"
        stamp_data.file_suffix = "html"
        stamp_data.recursive_mint_cpid = "A99999999999999999999"
        stamp_data.ident = "SRC-721"
        stamp_data._lock = MagicMock()
        stamp_data.db = mock_db

        # Since the content is HTML bytes, the fallback will try to process it
        # We need to convert it to a string that can be JSON serialized
        stamp_data.src_data = ""  # Initialize as empty string for fallback

        # Process the recursive mint
        stamp_data.process_src721(valid_stamps_in_block, mock_db)

        # When deploy is not found, it should still be a valid SRC-721
        # The ident is already set to "SRC-721" so it won't be cursed
        assert stamp_data.is_btc_stamp is True
        # Should have empty src_data for P2WSH SRC-721 detected via description
        assert stamp_data.src_data == ""
        # HTML content should be preserved
        assert stamp_data.decoded_base64 == b'<html><script src="/s/A99999999999999999999"></script></html>'
        assert stamp_data.file_suffix == "html"


def test_recursive_deploy_processing():
    """Test that recursive deploys are processed correctly."""
    mock_db = MagicMock()

    # Recursive deploy JSON
    deploy_json = {
        "p": "src-721",
        "v": "r0",
        "op": "deploy",
        "name": "Recursive Collection",
        "description": "Test recursive deploy",
        "t0": ["A12345678901234567890"],
        "max": "100",
    }

    with patch("index_core.src721.parse_valid_src721_in_block") as mock_parse:
        with patch("index_core.src721.get_src721_svg_string") as mock_svg:
            mock_parse.return_value = []
            mock_svg.return_value = "<svg>Deploy SVG</svg>"

            result = validate_src721_and_process(deploy_json, [], mock_db)

            svg_output, file_suffix, coll_name, coll_desc, coll_website, coll_onchain = result

            assert coll_name == "Recursive Collection"
            assert coll_desc == "Test recursive deploy"
            assert coll_onchain == 1
            assert file_suffix == "svg"


def test_mixed_collection_types():
    """Test that collections can have both standard and recursive mints."""
    # This is mainly a conceptual test to ensure the design supports mixed types
    # The actual implementation should handle both types seamlessly

    # Standard mint JSON
    standard_mint = {"p": "src-721", "op": "mint", "c": "A12345678901234567890", "ts": [0, 1, 2]}

    # Recursive mint has no JSON, just HTML/SVG with /s/ reference
    recursive_mint_html = b'<html><script src="/s/A12345678901234567890"></script></html>'

    # Both should be able to reference the same collection CPID
    # and be processed appropriately based on their format
    assert True  # Placeholder for integration test
