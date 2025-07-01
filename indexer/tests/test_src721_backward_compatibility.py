"""Tests to ensure backward compatibility with existing SRC-721 formats."""

import json
from unittest.mock import MagicMock, patch

import pytest

from index_core.src721 import (
    is_recursive_src721_deploy,
    validate_src721_and_process,
)


def test_standard_src721_deploy_not_affected():
    """Test that standard SRC-721 deploys (without version) are not affected."""
    mock_db = MagicMock()

    # Standard deploy without version field
    standard_deploy = {
        "p": "src-721",
        "op": "deploy",
        "name": "Standard Collection",
        "description": "Regular SRC-721 collection",
        "website": "https://example.com",
    }

    # Should NOT be detected as recursive
    assert is_recursive_src721_deploy(standard_deploy) is False

    # Should process normally
    with patch("index_core.src721.parse_valid_src721_in_block") as mock_parse:
        with patch("index_core.src721.get_src721_svg_string") as mock_svg:
            mock_parse.return_value = []
            mock_svg.return_value = "<svg>Standard Deploy</svg>"

            result = validate_src721_and_process(standard_deploy, [], mock_db)

            svg_output, file_suffix, coll_name, coll_desc, coll_website, coll_onchain = result

            # Verify standard processing
            assert coll_name == "Standard Collection"
            assert coll_desc == "Regular SRC-721 collection"
            assert coll_website == "https://example.com"
            assert file_suffix == "svg"
            assert coll_onchain == 1


def test_src721_v1_format_not_affected():
    """Test that SRC-721 with v:1 or other versions are not affected."""
    mock_db = MagicMock()

    # Deploy with v:1
    v1_deploy = {"p": "src-721", "v": "1", "op": "deploy", "name": "V1 Collection", "description": "Version 1 SRC-721"}

    # Should NOT be detected as recursive
    assert is_recursive_src721_deploy(v1_deploy) is False

    # Deploy with v:2
    v2_deploy = {"p": "src-721", "v": "2", "op": "deploy", "name": "V2 Collection"}

    assert is_recursive_src721_deploy(v2_deploy) is False


def test_standard_src721_mint_with_traits():
    """Test that standard SRC-721 mints with ts (trait selection) work normally."""
    from index_core.src721 import create_src721_mint_svg

    mock_db = MagicMock()

    # Standard mint with trait selection
    standard_mint = {
        "op": "mint",
        "c": "A12345678901234567890",  # Collection reference
        "ts": [0, 1, 2, 0, 1],  # Trait selections
    }

    # Mock collection in block
    valid_stamps = [
        {"cpid": "A12345678901234567890", "src_data": json.dumps({"p": "src-721", "op": "deploy", "name": "Trait Collection"})}
    ]

    with patch("index_core.src721.fetch_src721_collection") as mock_fetch_coll:
        with patch("index_core.src721.build_src721_stacked_svg") as mock_build:
            mock_fetch_coll.return_value = {"name": "Trait Collection"}
            mock_build.return_value = ("<svg>Stacked NFT</svg>", "Trait Collection")

            svg_output, collection_name = create_src721_mint_svg(standard_mint, valid_stamps, mock_db)

            assert svg_output == "<svg>Stacked NFT</svg>"
            assert collection_name == "Trait Collection"

            # Verify the standard mint flow was used
            mock_fetch_coll.assert_called_once()
            mock_build.assert_called_once()


def test_html_content_without_recursive_pattern():
    """Test that HTML content without /s/<CPID> pattern is not treated as SRC-721."""
    from index_core.src721 import is_recursive_src721_mint

    # HTML without recursive pattern
    html_content = b"<html><body><h1>Regular HTML stamp</h1></body></html>"
    is_recursive, cpid = is_recursive_src721_mint(html_content, "text/html")

    assert is_recursive is False
    assert cpid is None

    # SVG without recursive pattern
    svg_content = b'<svg><circle cx="50" cy="50" r="40"/></svg>'
    is_recursive, cpid = is_recursive_src721_mint(svg_content, "image/svg+xml")

    assert is_recursive is False
    assert cpid is None


def test_only_r0_version_triggers_recursive():
    """Test that only v:r0 (case-insensitive) triggers recursive behavior."""
    # Test various version values that should NOT be recursive
    non_recursive_versions = ["r1", "v0", "0", "recursive", "rec", None, ""]

    for version in non_recursive_versions:
        deploy = {"p": "src-721", "v": version, "op": "deploy", "name": f"Test {version}"}

        # These should not be recursive
        is_recursive = is_recursive_src721_deploy(deploy)
        assert is_recursive is False, f"Version {version} should not be recursive"

    # Both "r0" and "R0" should be recursive (case-insensitive)
    recursive_deploy_lower = {"p": "src-721", "v": "r0", "op": "deploy", "name": "Recursive Collection"}
    assert is_recursive_src721_deploy(recursive_deploy_lower) is True

    recursive_deploy_upper = {"p": "src-721", "v": "R0", "op": "deploy", "name": "Recursive Collection"}
    assert is_recursive_src721_deploy(recursive_deploy_upper) is True


def test_mixed_collection_backward_compatibility():
    """Test that collections can still have standard mints even with recursive deploys."""
    from index_core.models import StampData

    mock_db = MagicMock()

    # Create a recursive deploy in the block
    recursive_deploy = {
        "cpid": "A12345678901234567890",
        "src_data": json.dumps({"p": "src-721", "v": "r0", "op": "deploy", "name": "Mixed Collection"}),  # Recursive deploy
        "is_btc_stamp": True,
        "op": "deploy",  # Add op field for parse_valid_src721_in_block
    }

    valid_stamps_in_block = [recursive_deploy]

    # Test 1: Standard mint with JSON should still work
    stamp_data = StampData(
        tx_hash="standard_mint_tx",
        source="test_address",
        prev_tx_hash="prev_tx",
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

    # Set up standard mint data (JSON with traits)
    stamp_data.decoded_base64 = {"p": "src-721", "op": "mint", "c": "A12345678901234567890", "ts": [0, 1, 2]}
    stamp_data.ident = "SRC-721"
    stamp_data._lock = MagicMock()
    stamp_data.db = mock_db

    # Mock the validate_src721_and_process to avoid the unpacking error
    with patch("index_core.models.validate_src721_and_process") as mock_validate:
        # Return proper tuple with 6 values as expected
        mock_validate.return_value = (
            b"<svg>Standard mint</svg>",  # svg_output
            "svg",  # file_suffix
            "Mixed Collection",  # collection_name
            None,  # collection_description
            None,  # collection_website
            1,  # collection_onchain
        )

        # Process the standard mint
        stamp_data.process_src721(valid_stamps_in_block, mock_db)

        # Should use standard processing (not recursive)
        assert stamp_data.recursive_mint_cpid is None
        # Verify validate_src721_and_process was called
        assert mock_validate.call_count == 1
        # Verify it was processed as standard SRC-721
        assert stamp_data.is_btc_stamp is True
        assert stamp_data.file_suffix == "svg"
        assert stamp_data.stamp_mimetype == "image/svg+xml"


def test_cpid_pattern_strict_validation():
    """Test that CPID pattern matching is strict and doesn't match invalid formats."""
    from index_core.src721 import is_recursive_src721_mint

    # Valid CPID pattern
    valid_html = b'<script src="/s/A12345678901234567890"></script>'
    is_recursive, cpid = is_recursive_src721_mint(valid_html, "text/html")
    assert is_recursive is True
    assert cpid == "A12345678901234567890"

    # Invalid patterns that should NOT match
    invalid_patterns = [
        b'<script src="/s/12345678901234567890"></script>',  # Missing 'A'
        b'<script src="/s/A1234567890"></script>',  # Too short
        b'<script src="/s/A123456789012345678901"></script>',  # Too long
        b'<script src="/s/B12345678901234567890"></script>',  # Wrong prefix
        b'<script src="/stamp/A12345678901234567890"></script>',  # Wrong path
        b'<script src="s/A12345678901234567890"></script>',  # Missing leading slash
    ]

    for pattern in invalid_patterns:
        is_recursive, cpid = is_recursive_src721_mint(pattern, "text/html")
        assert is_recursive is False, f"Pattern {pattern} should not match"
        assert cpid is None
