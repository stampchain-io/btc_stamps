import json
import logging
import zlib
from unittest.mock import patch

import msgpack
import pytest

from index_core.models import StampData


class TestZlibCompression:
    """Test cases for zlib compression/decompression functionality in StampData"""

    def setup_method(self):
        """Setup test data for each test method"""
        self.base_stamp_data = {
            "tx_hash": "test_tx_hash",
            "source": "1SourceAddr",
            "prev_tx_hash": "prev_hash",
            "destination": "1DestAddr",
            "destination_nvalue": 0,
            "btc_amount": 0.0,
            "fee": 0.0,
            "data": "test_data",
            "decoded_tx": {},
            "keyburn": 1,
            "tx_index": 0,
            "block_index": 780000,
            "block_time": 1234567890,
            "is_op_return": False,
            "p2wsh_data": None,
        }

    def create_stamp_data(self, **overrides):
        """Helper to create StampData instance with optional overrides"""
        data = {**self.base_stamp_data, **overrides}
        return StampData(**data)

    def create_compressed_test_data(self, test_dict):
        """Helper to create zlib-compressed msgpack data"""
        # Pack the data with msgpack
        packed_data = msgpack.packb(test_dict)
        # Compress with zlib
        compressed_data = zlib.compress(packed_data)
        return compressed_data

    def test_zlib_decompress_valid_src20_data(self):
        """Test zlib decompression with valid SRC-20 data"""
        # Create test SRC-20 data
        src20_data = {"p": "SRC-20", "op": "DEPLOY", "tick": "TEST", "max": 1000000, "lim": 1000, "dec": 8}

        compressed_data = self.create_compressed_test_data(src20_data)
        stamp_data = self.create_stamp_data()

        # Call zlib_decompress
        stamp_data.zlib_decompress(compressed_data)

        # Verify results - after processing, decoded_base64 becomes a dict with lowercase keys
        expected_dict = {k.lower(): v for k, v in src20_data.items()}
        assert stamp_data.decoded_base64 == expected_dict
        assert stamp_data.file_suffix == "json"
        assert stamp_data.ident == "SRC-20"

    def test_zlib_decompress_valid_generic_json(self):
        """Test zlib decompression with generic JSON data"""
        generic_data = {
            "name": "Test Collection",
            "description": "A test collection",
            "items": [1, 2, 3],
            "metadata": {"version": "1.0"},
        }

        compressed_data = self.create_compressed_test_data(generic_data)
        stamp_data = self.create_stamp_data()

        stamp_data.zlib_decompress(compressed_data)

        # After processing, decoded_base64 becomes a dict with lowercase keys
        expected_dict = {k.lower(): v for k, v in generic_data.items()}
        assert stamp_data.decoded_base64 == expected_dict
        assert stamp_data.file_suffix == "json"
        assert stamp_data.ident == "UNKNOWN"  # Not a supported protocol

    def test_zlib_decompress_array_data(self):
        """Test zlib decompression with array data - should fail gracefully"""
        array_data = [{"id": 1, "name": "item1"}, {"id": 2, "name": "item2"}, {"id": 3, "name": "item3"}]

        compressed_data = self.create_compressed_test_data(array_data)
        stamp_data = self.create_stamp_data()

        # Array data should cause an AttributeError in decode_and_reformat_src_string
        # because arrays don't have .items() method
        with pytest.raises(AttributeError, match="'list' object has no attribute 'items'"):
            stamp_data.zlib_decompress(compressed_data)

    def test_zlib_decompress_nested_complex_data(self):
        """Test zlib decompression with deeply nested complex data"""
        complex_data = {
            "protocol": "SRC-721",
            "metadata": {
                "collection": {
                    "name": "Complex Collection",
                    "traits": [
                        {"type": "color", "value": "red", "rarity": 0.1},
                        {"type": "size", "value": "large", "rarity": 0.05},
                    ],
                },
                "attributes": {"strength": 95, "speed": 87, "intelligence": 92},
            },
            "references": ["ref1", "ref2", "ref3"],
        }

        compressed_data = self.create_compressed_test_data(complex_data)
        stamp_data = self.create_stamp_data()

        stamp_data.zlib_decompress(compressed_data)

        # After processing, decoded_base64 becomes a dict with lowercase keys
        expected_dict = {k.lower(): v for k, v in complex_data.items()}
        assert stamp_data.decoded_base64 == expected_dict
        assert stamp_data.file_suffix == "json"
        assert stamp_data.ident == "UNKNOWN"  # Not SRC-721 because it's protocol, not p

    def test_zlib_decompress_invalid_zlib_data(self):
        """Test zlib decompression with invalid zlib data"""
        invalid_compressed_data = b"not_valid_zlib_data"
        stamp_data = self.create_stamp_data()

        # Mock logger to capture the exclusion message
        with patch.object(logging.getLogger("index_core.models"), "info") as mock_logger:
            stamp_data.zlib_decompress(invalid_compressed_data)

            # Should log the exclusion and set ident to UNKNOWN
            mock_logger.assert_called_once()
            assert "EXCLUSION:" in mock_logger.call_args[0][0]
            assert stamp_data.ident == "UNKNOWN"

    def test_zlib_decompress_valid_zlib_invalid_msgpack(self):
        """Test zlib decompression with valid zlib but invalid msgpack data"""
        # Create valid zlib data but not valid msgpack
        invalid_msgpack_data = b"not_valid_msgpack"
        compressed_data = zlib.compress(invalid_msgpack_data)
        stamp_data = self.create_stamp_data()

        with patch.object(logging.getLogger("index_core.models"), "info") as mock_logger:
            stamp_data.zlib_decompress(compressed_data)

            # Should log msgpack exception and set ident to UNKNOWN
            mock_logger.assert_called_once()
            assert "EXCLUSION:" in mock_logger.call_args[0][0]
            assert stamp_data.ident == "UNKNOWN"

    def test_zlib_decompress_msgpack_extra_data_error(self):
        """Test zlib decompression handling msgpack ExtraData exception"""
        # Create msgpack data with extra bytes to trigger ExtraData exception
        valid_data = {"test": "data"}
        packed_data = msgpack.packb(valid_data) + b"extra_bytes"
        compressed_data = zlib.compress(packed_data)
        stamp_data = self.create_stamp_data()

        with patch.object(logging.getLogger("index_core.models"), "info") as mock_logger:
            stamp_data.zlib_decompress(compressed_data)

            # Should handle ExtraData exception gracefully
            mock_logger.assert_called_once()
            assert "EXCLUSION:" in mock_logger.call_args[0][0]
            assert stamp_data.ident == "UNKNOWN"

    def test_zlib_decompress_type_error(self):
        """Test zlib decompression handling TypeError"""
        stamp_data = self.create_stamp_data()

        # Pass None to trigger TypeError
        with patch.object(logging.getLogger("index_core.models"), "info") as mock_logger:
            stamp_data.zlib_decompress(None)

            # Should handle TypeError gracefully
            mock_logger.assert_called_once()
            assert "EXCLUSION:" in mock_logger.call_args[0][0]
            assert stamp_data.ident == "UNKNOWN"

    def test_zlib_decompress_empty_data(self):
        """Test zlib decompression with empty compressed data"""
        # Create compressed empty data
        empty_data = {}
        compressed_data = self.create_compressed_test_data(empty_data)
        stamp_data = self.create_stamp_data()

        stamp_data.zlib_decompress(compressed_data)

        # After processing, empty dict stays as empty dict
        assert stamp_data.decoded_base64 == empty_data
        assert stamp_data.file_suffix == "json"
        assert stamp_data.ident == "UNKNOWN"

    def test_zlib_decompress_unicode_data(self):
        """Test zlib decompression with unicode characters"""
        unicode_data = {
            "name": "测试集合",  # Chinese characters
            "description": "Tëst cøllëctïön wïth ünïcødë",  # Various accented characters
            "emoji": "🚀🌟💎",  # Emoji
            "symbols": "α β γ δ ε",  # Greek symbols
        }

        compressed_data = self.create_compressed_test_data(unicode_data)
        stamp_data = self.create_stamp_data()

        stamp_data.zlib_decompress(compressed_data)

        # After processing, decoded_base64 becomes a dict with lowercase keys
        expected_dict = {k.lower(): v for k, v in unicode_data.items()}
        assert stamp_data.decoded_base64 == expected_dict
        assert stamp_data.file_suffix == "json"
        assert stamp_data.ident == "UNKNOWN"

    def test_zlib_decompress_large_data(self):
        """Test zlib decompression with large dataset"""
        # Create a large dataset
        large_data = {
            "items": [{"id": i, "name": f"item_{i}", "value": i * 100} for i in range(1000)],
            "metadata": {"total_items": 1000, "generated_at": "2024-01-01T00:00:00Z", "version": "2.0"},
        }

        compressed_data = self.create_compressed_test_data(large_data)
        stamp_data = self.create_stamp_data()

        stamp_data.zlib_decompress(compressed_data)

        # After processing, decoded_base64 becomes a dict with lowercase keys
        expected_dict = {k.lower(): v for k, v in large_data.items()}
        assert stamp_data.decoded_base64 == expected_dict
        assert stamp_data.file_suffix == "json"
        assert stamp_data.ident == "UNKNOWN"

    @patch("index_core.models.StampData.handle_json_string")
    def test_zlib_decompress_calls_handle_json_string(self, mock_handle_json):
        """Test that zlib_decompress calls handle_json_string after successful decompression"""
        test_data = {"test": "data"}
        compressed_data = self.create_compressed_test_data(test_data)
        stamp_data = self.create_stamp_data()

        stamp_data.zlib_decompress(compressed_data)

        # Verify handle_json_string was called
        mock_handle_json.assert_called_once()

    def test_handle_bytes_again_triggers_zlib_decompress(self):
        """Test that handle_bytes_again calls zlib_decompress when file_suffix is 'zlib'"""
        test_data = {"protocol": "test"}
        compressed_data = self.create_compressed_test_data(test_data)
        stamp_data = self.create_stamp_data()
        stamp_data.decoded_base64 = compressed_data

        # Mock update_file_suffix_and_mime_type to set file_suffix to 'zlib'
        with patch.object(stamp_data, "update_file_suffix_and_mime_type") as mock_update:
            mock_update.side_effect = lambda data: setattr(stamp_data, "file_suffix", "zlib")

            with patch.object(stamp_data, "zlib_decompress") as mock_zlib_decompress:
                stamp_data.handle_bytes_again()

                # Verify zlib_decompress was called with the compressed data
                mock_zlib_decompress.assert_called_once_with(compressed_data)

    def test_compression_ratio_effectiveness(self):
        """Test that zlib compression is effective for JSON data"""
        # Create repetitive data that should compress well
        repetitive_data = {"repeated_field_" + str(i): "same_value_repeated_many_times" for i in range(100)}

        # Convert to JSON and measure original size
        json_string = json.dumps(repetitive_data)
        original_size = len(json_string.encode("utf-8"))

        # Compress and measure compressed size
        compressed_data = self.create_compressed_test_data(repetitive_data)
        compressed_size = len(compressed_data)

        # Verify compression is effective (should be much smaller)
        compression_ratio = compressed_size / original_size
        assert compression_ratio < 0.1  # Should compress to less than 10% of original size

        # Verify we can decompress it correctly
        stamp_data = self.create_stamp_data()
        stamp_data.zlib_decompress(compressed_data)

        # After processing, decoded_base64 becomes a dict with lowercase keys
        expected_dict = {k.lower(): v for k, v in repetitive_data.items()}
        assert stamp_data.decoded_base64 == expected_dict
        assert stamp_data.file_suffix == "json"
        assert stamp_data.ident == "UNKNOWN"

    def test_round_trip_compression_decompression(self):
        """Test complete round-trip: compress data then decompress it back"""
        original_data = {
            "p": "SRC-721",
            "collection": {
                "name": "Round Trip Test",
                "items": [
                    {"id": 1, "traits": {"color": "blue", "rarity": "common"}},
                    {"id": 2, "traits": {"color": "red", "rarity": "rare"}},
                    {"id": 3, "traits": {"color": "gold", "rarity": "legendary"}},
                ],
            },
            "metadata": {"version": "1.0", "created": "2024-01-01"},
        }

        # Compress the data
        compressed_data = self.create_compressed_test_data(original_data)

        # Decompress using our method
        stamp_data = self.create_stamp_data()
        stamp_data.zlib_decompress(compressed_data)

        # After processing, decoded_base64 becomes a dict with lowercase keys
        expected_dict = {k.lower(): v for k, v in original_data.items()}
        assert stamp_data.decoded_base64 == expected_dict
        assert stamp_data.file_suffix == "json"
        assert stamp_data.ident == "SRC-721"  # Should be detected as SRC-721
