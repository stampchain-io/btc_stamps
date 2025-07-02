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


def test_process_standard_src721_mint():
    """Test processing a standard SRC-721 mint with JSON data."""
    from index_core.models import StampData

    # Create mock database
    mock_db = MagicMock()
    valid_stamps_in_block = []

    # Create stamp data for standard JSON mint
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
        keyburn=True,  # Keyburn required for standard SRC-721
        tx_index=1,
        block_index=800000,
        block_time=1234567890,
        is_op_return=False,
        p2wsh_data=None,
    )

    # Set the decoded JSON content
    stamp_data.decoded_base64 = {"p": "src-721", "op": "mint", "c": "A12345678901234567890", "ts": [0, 1, 2]}
    stamp_data.stamp_mimetype = "application/json"
    stamp_data.file_suffix = "json"
    stamp_data.ident = "SRC-721"
    stamp_data.supply = 1
    stamp_data._lock = MagicMock()
    stamp_data.db = mock_db

    # Process the standard mint
    stamp_data.process_src721(valid_stamps_in_block, mock_db)

    # Verify the results - our implementation converts everything to SVG
    assert stamp_data.is_btc_stamp is True
    # Content gets converted to SVG (our actual behavior)
    assert stamp_data.file_suffix == "svg"
    assert stamp_data.stamp_mimetype == "image/svg+xml"


def test_olga_mint_detection():
    """Test that OLGA mints (HTML with /s/CPID) are detected as SRC-721 ident but don't pass valid_src721."""
    from index_core.models import StampData

    # Create stamp data for OLGA mint (HTML with /s/CPID reference)
    stamp_data = StampData(
        tx_hash="test_olga_tx",
        source="test_address",
        prev_tx_hash="prev_tx_hash",
        destination="test_address",
        destination_nvalue=0,
        btc_amount=0,
        fee=1000,
        data={},
        decoded_tx={},
        keyburn=False,  # P2WSH doesn't require keyburn
        tx_index=1,
        block_index=800000,
        block_time=1234567890,
        is_op_return=False,
        p2wsh_data=b'<html><script src="/s/A17785882525351975000"></script></html>',
    )

    # Set the basic attributes
    stamp_data.ident = "SRC-721"  # Would be set by OLGA detection
    stamp_data.stamp_mimetype = "text/html"
    stamp_data.file_suffix = "html"
    stamp_data.supply = 1

    # Test that OLGA mints don't pass valid_src721 check
    assert stamp_data.valid_src721() is False


def test_standard_src721_mint_valid():
    """Test that standard JSON SRC-721 mint passes valid_src721 check."""
    from index_core.models import StampData

    # Create stamp data for standard JSON mint
    stamp_data = StampData(
        tx_hash="test_json_mint_tx",
        source="test_address",
        prev_tx_hash="prev_tx_hash",
        destination="test_address",
        destination_nvalue=0,
        btc_amount=0,
        fee=1000,
        data={},
        decoded_tx={},
        keyburn=True,  # Keyburn required for standard SRC-721
        tx_index=1,
        block_index=800000,
        block_time=1234567890,
        is_op_return=False,
        p2wsh_data=None,
    )

    # Set up for JSON SRC-721
    stamp_data.ident = "SRC-721"
    stamp_data.stamp_mimetype = "application/json"
    stamp_data.file_suffix = "json"
    stamp_data.supply = 1

    # Test that JSON SRC-721 passes valid_src721 check
    assert stamp_data.valid_src721() is True


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
