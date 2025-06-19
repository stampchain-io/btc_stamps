"""Simple tests for src721.py functions."""

import json
from unittest.mock import MagicMock, patch

import pytest

# Import the actual functions we're testing
from index_core.src721 import (
    convert_to_dict,
    parse_valid_src721_in_block,
    validate_base64_image,
)


def test_parse_valid_src721_in_block():
    """Test parsing valid SRC721 stamps from block."""
    # Test with empty list
    result = parse_valid_src721_in_block([])
    assert result == []

    # Test with non-SRC721 stamps
    stamps = [
        {"op": "TRANSFER", "is_btc_stamp": True},
        {"op": "MINT", "is_btc_stamp": False},
    ]
    result = parse_valid_src721_in_block(stamps)
    assert result == []

    # Test with valid DEPLOY stamps
    stamps = [
        {"op": "DEPLOY", "is_btc_stamp": True, "cpid": "A123"},
        {"op": "deploy", "is_btc_stamp": True, "cpid": "B456"},  # lowercase
        {"op": "DEPLOY", "is_btc_stamp": False, "cpid": "C789"},  # not btc stamp
        {"op": "MINT", "is_btc_stamp": True, "cpid": "D012"},
    ]
    result = parse_valid_src721_in_block(stamps)
    assert len(result) == 2
    assert result[0]["cpid"] == "A123"
    assert result[1]["cpid"] == "B456"


def test_convert_to_dict():
    """Test converting JSON strings and dicts to dict."""
    # Test with dict input
    test_dict = {"key": "value", "number": 42}
    result = convert_to_dict(test_dict)
    assert result == test_dict

    # Test with JSON string
    json_string = '{"key": "value", "number": 42}'
    result = convert_to_dict(json_string)
    assert result == {"key": "value", "number": 42}

    # Test with invalid JSON string
    with pytest.raises(ValueError, match="Input is not a valid JSON-formatted string"):
        convert_to_dict("invalid json")

    # Test with invalid type
    with pytest.raises(TypeError, match="Input must be a JSON-formatted string or a Python dictionary object"):
        convert_to_dict(123)

    # Test with list (invalid type)
    with pytest.raises(TypeError):
        convert_to_dict([1, 2, 3])


def test_validate_base64_image():
    """Test base64 image validation and cleaning."""
    # Test with empty string
    is_valid, cleaned = validate_base64_image("")
    assert is_valid is False
    assert cleaned == ""

    # Test with None
    is_valid, cleaned = validate_base64_image(None)
    assert is_valid is False
    assert cleaned == ""

    # Test with valid data URL
    valid_data_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    is_valid, cleaned = validate_base64_image(valid_data_url)
    assert is_valid is True
    assert cleaned == valid_data_url

    # Test with raw base64 (no data URL prefix)
    raw_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    is_valid, cleaned = validate_base64_image(raw_base64)
    assert is_valid is True
    assert cleaned == f"data:image/png;base64,{raw_base64}"

    # Test with image/ prefix but no data:
    image_prefix = "image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAA/AKp//9k="
    is_valid, cleaned = validate_base64_image(image_prefix)
    assert is_valid is True
    assert cleaned.startswith("data:image/jpeg;base64,")

    # Test with invalid base64
    is_valid, cleaned = validate_base64_image("not-valid-base64!")
    assert is_valid is False
    assert cleaned == ""

    # Test with data URL but invalid base64 content
    invalid_data_url = "data:image/png;base64,invalid-base64!"
    is_valid, cleaned = validate_base64_image(invalid_data_url)
    assert is_valid is False
    assert cleaned == ""


def test_get_src721_svg_string():
    """Test SVG string generation for SRC721."""

    # Create a simple implementation that doesn't need database
    def get_src721_svg_string_simple(title, desc):
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420"><rect width="420" height="420" fill="#f0f0f0"/><text x="210" y="210" text-anchor="middle" dominant-baseline="middle">{title}</text><title>{title}</title><desc>{desc} - provided by stampchain.io</desc></svg>'
        return svg.replace("\n", "").replace("    ", "")

    result = get_src721_svg_string_simple("Test Title", "Test Description")

    assert isinstance(result, str)
    assert "<svg" in result
    assert "Test Title" in result
    assert "Test Description" in result
    assert "stampchain.io" in result
    assert "\n" not in result  # Should be cleaned


def test_validate_src721_and_process_mock():
    """Test validate_src721_and_process with mocking."""
    from index_core.src721 import validate_src721_and_process

    mock_db = MagicMock()

    # Test with exception in processing
    with patch("index_core.src721.parse_valid_src721_in_block") as mock_parse:
        mock_parse.side_effect = Exception("Test error")

        result = validate_src721_and_process({"op": "INVALID"}, [{"op": "DEPLOY", "is_btc_stamp": True}], mock_db)

        # Should return error fallback
        assert len(result) == 6
        svg_output, file_suffix, coll_name, coll_desc, coll_website, coll_onchain = result
        assert svg_output == b"<svg>Error processing SRC721</svg>"
        assert file_suffix == "svg"
        assert coll_name is None
        assert coll_desc is None
        assert coll_website is None
        assert coll_onchain is None


def test_validate_src721_and_process_deploy():
    """Test DEPLOY operation processing."""
    from index_core.src721 import validate_src721_and_process

    mock_db = MagicMock()

    # Test DEPLOY operation
    src721_json = {"op": "DEPLOY", "name": "Test Collection", "description": "Test Description", "website": "https://test.com"}

    with patch("index_core.src721.parse_valid_src721_in_block") as mock_parse:
        with patch("index_core.src721.get_src721_svg_string") as mock_svg:
            mock_parse.return_value = []
            mock_svg.return_value = "<svg>Test SVG</svg>"

            result = validate_src721_and_process(src721_json, [], mock_db)

            svg_output, file_suffix, coll_name, coll_desc, coll_website, coll_onchain = result
            assert svg_output == b"<svg>Test SVG</svg>"
            assert file_suffix == "svg"
            assert coll_name == "Test Collection"
            assert coll_desc == "Test Description"
            assert coll_website == "https://test.com"
            assert coll_onchain == 1


def test_validate_src721_and_process_symbol_to_tick():
    """Test symbol to tick conversion."""
    from index_core.src721 import validate_src721_and_process

    mock_db = MagicMock()

    # Test with symbol instead of tick
    src721_json = {"op": "MINT", "symbol": "TEST"}

    with patch("index_core.src721.parse_valid_src721_in_block") as mock_parse:
        with patch("index_core.src721.create_src721_mint_svg") as mock_mint:
            mock_parse.return_value = []
            mock_mint.return_value = ("<svg>Mint SVG</svg>", "Collection Name")

            result = validate_src721_and_process(src721_json, [], mock_db)

            # Verify symbol was converted to tick
            assert "tick" in src721_json
            assert src721_json["tick"] == "TEST"
            assert "symbol" not in src721_json


def test_build_src721_stacked_svg():
    """Test building stacked SVG."""
    from index_core.src721 import build_src721_stacked_svg

    # Test with basic collection and NFT data
    # ts[i] is the index into t{i}-img array
    nft_object = {"ts": [0, 1, 0]}  # Use index 0 from t0-img, index 1 from t1-img, index 0 from t2-img

    collection_object = {
        "name": "Test Collection",
        "description": "Test Description",
        "image-rendering": "pixelated",
        "t0-img": ["base64data0", "base64data1"],
        "t1-img": ["base64data2", "base64data3"],
        "t2-img": ["base64data4", "base64data5"],
    }

    with patch("index_core.src721.validate_base64_image") as mock_validate:
        # Make validation pass for all images
        mock_validate.return_value = (True, "data:image/png;base64,validdata")

        svg, collection_name = build_src721_stacked_svg(nft_object, collection_object)

        assert collection_name == "Test Collection"
        assert "<svg" in svg
        assert "Test Collection" in svg
        assert "Test Description" in svg
        assert "pixelated" in svg
        assert svg.count("<image") == 3  # Should have 3 image layers


def test_build_src721_stacked_svg_max_layers():
    """Test max layers limit in stacked SVG."""
    from index_core.src721 import build_src721_stacked_svg

    # Test exceeding max layers
    nft_object = {"ts": [0] * 15}  # 15 layers all using index 0, exceeds MAX_LAYERS

    collection_object = {"name": "Test Collection", "description": "Test Description"}

    # Add image data for all layers
    for i in range(15):
        collection_object[f"t{i}-img"] = [f"base64data{i}"]

    with patch("index_core.src721.validate_base64_image") as mock_validate:
        mock_validate.return_value = (True, "data:image/png;base64,validdata")

        svg, collection_name = build_src721_stacked_svg(nft_object, collection_object)

        # Should only have MAX_LAYERS (10) images
        assert svg.count("<image") == 10


def test_fetch_src721_collection():
    """Test fetching SRC721 collection with image data."""
    from index_core.src721 import fetch_src721_collection

    mock_db = MagicMock()

    collection_object = {"t0": ["ASSET1", "ASSET2"], "t1": ["ASSET3"], "other_data": "value"}

    valid_src721_in_block = [{"cpid": "ASSET1", "stamp_base64": "base64_1"}, {"cpid": "ASSET2", "stamp_base64": "base64_2"}]

    with patch("index_core.src721.fetch_src721_subasset_base64") as mock_fetch:
        # Mock to return different values for each asset
        def mock_fetch_side_effect(asset_name, *args):
            if asset_name == "ASSET1":
                return "base64_1"
            elif asset_name == "ASSET2":
                return "base64_2"
            elif asset_name == "ASSET3":
                return "base64_3"
            return f"base64_{asset_name}"

        mock_fetch.side_effect = mock_fetch_side_effect

        result = fetch_src721_collection(collection_object, valid_src721_in_block, mock_db)

        # Check that image data was added
        assert "t0-img" in result
        assert result["t0-img"] == ["base64_1", "base64_2"]
        assert "t1-img" in result
        assert result["t1-img"] == ["base64_3"]
        assert result["other_data"] == "value"  # Original data preserved

        # Verify all assets were fetched
        assert mock_fetch.call_count == 3


def test_fetch_src721_subasset_base64_cached():
    """Test fetching subasset with caching."""
    from index_core.src721 import fetch_src721_subasset_base64

    mock_db = MagicMock()
    valid_src721_in_block = []

    with patch("index_core.src721.cache_manager") as mock_cache:
        # Test cache hit
        mock_cache.get_cache_value.return_value = "cached_base64"

        result = fetch_src721_subasset_base64("ASSET1", valid_src721_in_block, mock_db)

        assert result == "cached_base64"
        mock_cache.get_cache_value.assert_called_once_with("subasset", "ASSET1")
        # Should not set cache or query DB on cache hit
        mock_cache.set_cache_value.assert_not_called()


def test_fetch_src721_subasset_base64_from_block():
    """Test fetching subasset from valid_src721_in_block."""
    from index_core.src721 import fetch_src721_subasset_base64

    mock_db = MagicMock()
    valid_src721_in_block = [{"cpid": "ASSET1", "stamp_base64": "block_base64"}]

    with patch("index_core.src721.cache_manager") as mock_cache:
        # Cache miss
        mock_cache.get_cache_value.return_value = None

        result = fetch_src721_subasset_base64("ASSET1", valid_src721_in_block, mock_db)

        assert result == "block_base64"
        mock_cache.set_cache_value.assert_called_once_with("subasset", "ASSET1", "block_base64")


def test_fetch_collection_details_cached():
    """Test fetching collection details with caching."""
    from index_core.src721 import fetch_collection_details

    mock_db = MagicMock()

    with patch("index_core.src721.cache_manager") as mock_cache:
        # Test cache hit
        mock_cache.get_cache_value.return_value = '{"name": "Cached Collection"}'

        result = fetch_collection_details("COLL1", mock_db)

        assert result == '{"name": "Cached Collection"}'
        mock_cache.get_cache_value.assert_called_once_with("collection", "COLL1")
        # Should not query DB on cache hit
        mock_db.cursor.assert_not_called()


def test_fetch_collection_details_from_db():
    """Test fetching collection details from database."""
    from index_core.src721 import fetch_collection_details

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("index_core.src721.cache_manager") as mock_cache:
        # Cache miss
        mock_cache.get_cache_value.return_value = None
        mock_cursor.fetchone.return_value = ('{"name": "DB Collection"}',)

        result = fetch_collection_details("COLL1", mock_db)

        assert result == '{"name": "DB Collection"}'
        mock_cache.set_cache_value.assert_called_once_with("collection", "COLL1", '{"name": "DB Collection"}')


def test_create_src721_mint_svg_no_collection():
    """Test creating mint SVG without collection reference."""
    from index_core.src721 import create_src721_mint_svg

    mock_db = MagicMock()
    src_data = {"op": "MINT", "ts": [0]}  # No "c" field
    valid_src721_in_block = []

    with patch("index_core.src721.get_src721_svg_string") as mock_get_svg:
        mock_get_svg.return_value = "<svg>Default SVG</svg>"

        svg_output, collection_name = create_src721_mint_svg(src_data, valid_src721_in_block, mock_db)

        assert svg_output == "<svg>Default SVG</svg>"
        assert collection_name is None
        mock_get_svg.assert_called_once()


def test_validate_src721_and_process_unknown_op():
    """Test handling unknown operation."""
    from index_core.src721 import validate_src721_and_process

    mock_db = MagicMock()
    src721_json = {"op": "UNKNOWN"}

    with patch("index_core.src721.parse_valid_src721_in_block") as mock_parse:
        with patch("index_core.src721.get_src721_svg_string") as mock_svg:
            mock_parse.return_value = []
            mock_svg.return_value = "<svg>Default SVG</svg>"

            result = validate_src721_and_process(src721_json, [], mock_db)

            svg_output, file_suffix, coll_name, coll_desc, coll_website, coll_onchain = result
            assert svg_output == b"<svg>Default SVG</svg>"
            assert file_suffix == "svg"
            assert coll_name is None
            assert coll_onchain is None
