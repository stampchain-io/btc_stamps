import hashlib
import unittest
from unittest.mock import Mock, patch

from index_core.files import get_fileobj_and_md5


class TestFilesUtils(unittest.TestCase):
    """Test file utility functions."""

    def test_get_fileobj_and_md5_normal_data(self):
        """Test get_fileobj_and_md5 with normal binary data."""
        test_data = b"Hello, World!"
        file_obj, file_obj_md5 = get_fileobj_and_md5(test_data)

        # Verify file object
        self.assertIsNotNone(file_obj)
        file_obj.seek(0)
        self.assertEqual(file_obj.read(), test_data)

        # Verify MD5 hash
        expected_md5 = hashlib.md5(test_data, usedforsecurity=False).hexdigest()
        self.assertEqual(file_obj_md5, expected_md5)

    def test_get_fileobj_and_md5_empty_data(self):
        """Test get_fileobj_and_md5 with empty data."""
        test_data = b""
        file_obj, file_obj_md5 = get_fileobj_and_md5(test_data)

        # Verify file object
        self.assertIsNotNone(file_obj)
        file_obj.seek(0)
        self.assertEqual(file_obj.read(), test_data)

        # Verify MD5 hash of empty data
        expected_md5 = hashlib.md5(b"", usedforsecurity=False).hexdigest()
        self.assertEqual(file_obj_md5, expected_md5)

    def test_get_fileobj_and_md5_none_input(self):
        """Test get_fileobj_and_md5 with None input."""
        file_obj, file_obj_md5 = get_fileobj_and_md5(None)

        self.assertIsNone(file_obj)
        self.assertIsNone(file_obj_md5)

    def test_get_fileobj_and_md5_large_data(self):
        """Test get_fileobj_and_md5 with larger data."""
        test_data = b"x" * 10000  # 10KB of data
        file_obj, file_obj_md5 = get_fileobj_and_md5(test_data)

        # Verify file object
        self.assertIsNotNone(file_obj)
        file_obj.seek(0)
        self.assertEqual(file_obj.read(), test_data)

        # Verify MD5 hash
        expected_md5 = hashlib.md5(test_data, usedforsecurity=False).hexdigest()
        self.assertEqual(file_obj_md5, expected_md5)

    def test_get_fileobj_and_md5_binary_data(self):
        """Test get_fileobj_and_md5 with binary data."""
        test_data = bytes(range(256))  # All possible byte values
        file_obj, file_obj_md5 = get_fileobj_and_md5(test_data)

        # Verify file object
        self.assertIsNotNone(file_obj)
        file_obj.seek(0)
        self.assertEqual(file_obj.read(), test_data)

        # Verify MD5 hash
        expected_md5 = hashlib.md5(test_data, usedforsecurity=False).hexdigest()
        self.assertEqual(file_obj_md5, expected_md5)

    def test_get_fileobj_and_md5_consistent_hash(self):
        """Test that MD5 hash is consistent for same data."""
        test_data = b"Consistency test data"

        file_obj1, md5_1 = get_fileobj_and_md5(test_data)
        file_obj2, md5_2 = get_fileobj_and_md5(test_data)

        self.assertEqual(md5_1, md5_2)

        # Verify both file objects contain same data
        file_obj1.seek(0)
        file_obj2.seek(0)
        self.assertEqual(file_obj1.read(), file_obj2.read())

    def test_get_fileobj_and_md5_file_position(self):
        """Test that file object positioning after MD5 calculation."""
        test_data = b"Position test data"
        file_obj, file_obj_md5 = get_fileobj_and_md5(test_data)

        # File should be positioned at end after MD5 calculation
        self.assertEqual(file_obj.tell(), len(test_data))

        # Reset to beginning and verify we can read full content
        file_obj.seek(0)
        content = file_obj.read()
        self.assertEqual(content, test_data)

        # Position should now be at end again
        self.assertEqual(file_obj.tell(), len(test_data))

    @patch("index_core.files.hashlib.md5")
    def test_get_fileobj_and_md5_exception_handling(self, mock_md5):
        """Test exception handling in get_fileobj_and_md5."""
        # Mock md5 to raise an exception
        mock_md5.side_effect = Exception("MD5 calculation failed")

        test_data = b"test data"

        with self.assertRaises(Exception) as context:
            get_fileobj_and_md5(test_data)

        self.assertEqual(str(context.exception), "MD5 calculation failed")

    def test_get_fileobj_and_md5_known_hash_values(self):
        """Test MD5 calculation against known values."""
        # Test with known MD5 values
        test_cases = [
            (b"", "d41d8cd98f00b204e9800998ecf8427e"),  # Empty string
            (b"a", "0cc175b9c0f1b6a831c399e269772661"),  # Single character
            (b"abc", "900150983cd24fb0d6963f7d28e17f72"),  # Short string
            (b"The quick brown fox jumps over the lazy dog", "9e107d9d372bb6826bd81d3542a419d6"),
        ]

        for data, expected_md5 in test_cases:
            file_obj, file_obj_md5 = get_fileobj_and_md5(data)
            self.assertEqual(file_obj_md5, expected_md5, f"MD5 mismatch for data: {data}")


if __name__ == "__main__":
    unittest.main()
