import unittest
from unittest.mock import Mock, patch

from index_core.stamp import encode_and_store_file
from index_core.util import calculate_file_size


class TestFilesizeTracking(unittest.TestCase):

    def test_calculate_file_size_normal(self):
        """Test file size calculation with normal data."""
        data = b"test data"
        self.assertEqual(calculate_file_size(data), 9)

    def test_calculate_file_size_empty(self):
        """Test file size calculation with empty data."""
        self.assertEqual(calculate_file_size(b""), 0)

    def test_calculate_file_size_none(self):
        """Test file size calculation with None."""
        self.assertEqual(calculate_file_size(None), 0)

    def test_calculate_file_size_large(self):
        """Test file size calculation with large data."""
        data = b"x" * 1024 * 1024  # 1MB
        self.assertEqual(calculate_file_size(data), 1024 * 1024)

    def test_calculate_file_size_unicode(self):
        """Test file size calculation with unicode data."""
        data = "Hello 世界".encode("utf-8")
        # "Hello " = 6 bytes, "世界" = 6 bytes (3 bytes each in UTF-8)
        self.assertEqual(calculate_file_size(data), 12)

    @patch("index_core.stamp.store_files")
    def test_encode_and_store_file_with_size_calculation(self, mock_store_files):
        """Test that encode_and_store_file calculates and returns file size."""
        # Mock the store_files function
        mock_store_files.return_value = ("mock_hash", "mock_filename")

        # Test data
        db = Mock()
        tx_hash = "test_hash"
        file_suffix = "txt"
        decoded_base64 = "test content"
        stamp_mimetype = "text/plain"

        # Call the function
        file_hash, filename, file_size_bytes = encode_and_store_file(db, tx_hash, file_suffix, decoded_base64, stamp_mimetype)

        # Verify results
        self.assertEqual(file_hash, "mock_hash")
        self.assertEqual(filename, "mock_filename")
        self.assertEqual(file_size_bytes, len("test content".encode("utf-8")))

        # Verify store_files was called with correct parameters
        mock_store_files.assert_called_once_with(db, "test_hash.txt", "test content".encode("utf-8"), "text/plain")

    @patch("index_core.stamp.store_files")
    def test_encode_and_store_file_with_dict_input(self, mock_store_files):
        """Test encode_and_store_file with dictionary input."""
        # Mock the store_files function
        mock_store_files.return_value = ("mock_hash", "mock_filename")

        # Test data
        db = Mock()
        tx_hash = "test_hash"
        file_suffix = "json"
        decoded_base64 = {"key": "value", "number": 123}
        stamp_mimetype = "application/json"

        # Call the function
        file_hash, filename, file_size_bytes = encode_and_store_file(db, tx_hash, file_suffix, decoded_base64, stamp_mimetype)

        # Verify results
        self.assertEqual(file_hash, "mock_hash")
        self.assertEqual(filename, "mock_filename")

        # Calculate expected size
        import json

        expected_json = json.dumps(decoded_base64)
        expected_size = len(expected_json.encode("utf-8"))
        self.assertEqual(file_size_bytes, expected_size)

    @patch("index_core.stamp.store_files")
    def test_encode_and_store_file_with_bytes_input(self, mock_store_files):
        """Test encode_and_store_file with bytes input."""
        # Mock the store_files function
        mock_store_files.return_value = ("mock_hash", "mock_filename")

        # Test data
        db = Mock()
        tx_hash = "test_hash"
        file_suffix = "bin"
        decoded_base64 = b"binary data content"
        stamp_mimetype = "application/octet-stream"

        # Call the function
        file_hash, filename, file_size_bytes = encode_and_store_file(db, tx_hash, file_suffix, decoded_base64, stamp_mimetype)

        # Verify results
        self.assertEqual(file_hash, "mock_hash")
        self.assertEqual(filename, "mock_filename")
        self.assertEqual(file_size_bytes, len(b"binary data content"))

    def test_encode_and_store_file_no_suffix(self):
        """Test encode_and_store_file when no file suffix is provided."""
        db = Mock()
        tx_hash = "test_hash"
        file_suffix = None
        decoded_base64 = "test content"
        stamp_mimetype = "text/plain"

        # Call the function
        file_hash, filename, file_size_bytes = encode_and_store_file(db, tx_hash, file_suffix, decoded_base64, stamp_mimetype)

        # Verify results for no suffix case
        self.assertIsNone(file_hash)
        self.assertIsNone(filename)
        self.assertEqual(file_size_bytes, 0)


if __name__ == "__main__":
    unittest.main()
