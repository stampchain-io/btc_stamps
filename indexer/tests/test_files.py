"""Tests for files module."""

import hashlib
import io
import os
import tempfile
import unittest
from unittest import mock

import config
from index_core.files import get_fileobj_and_md5, store_files, store_files_to_disk


class TestFiles(unittest.TestCase):
    """Test file handling functions."""

    def test_get_fileobj_and_md5_valid_input(self):
        """Test get_fileobj_and_md5 with valid input."""
        test_data = b"Hello, World!"
        file_obj, md5_hash = get_fileobj_and_md5(test_data)

        # Verify file object
        self.assertIsInstance(file_obj, io.BytesIO)
        file_obj.seek(0)
        self.assertEqual(file_obj.read(), test_data)

        # Verify MD5 hash
        expected_md5 = hashlib.md5(test_data, usedforsecurity=False).hexdigest()
        self.assertEqual(md5_hash, expected_md5)

    def test_get_fileobj_and_md5_none_input(self):
        """Test get_fileobj_and_md5 with None input."""
        file_obj, md5_hash = get_fileobj_and_md5(None)

        self.assertIsNone(file_obj)
        self.assertIsNone(md5_hash)

    def test_get_fileobj_and_md5_exception(self):
        """Test get_fileobj_and_md5 with invalid input that causes exception."""
        # Mock BytesIO to raise an exception
        with mock.patch("io.BytesIO", side_effect=Exception("Test error")):
            with self.assertRaises(Exception) as context:
                get_fileobj_and_md5(b"data")
            self.assertEqual(str(context.exception), "Test error")

    @mock.patch("index_core.files.config.STORE_FILES", False)
    def test_store_files_disabled(self):
        """Test store_files when storage is disabled."""
        test_data = b"Test data"
        filename = "test.txt"

        md5_hash, returned_filename = store_files(None, filename, test_data, "text/plain")

        # Should still calculate MD5 and return filename
        expected_md5 = hashlib.md5(test_data, usedforsecurity=False).hexdigest()
        self.assertEqual(md5_hash, expected_md5)
        self.assertEqual(returned_filename, filename)

    @mock.patch("index_core.files.config.STORE_FILES", True)
    @mock.patch("index_core.files.config.AWS_SECRET_ACCESS_KEY", None)
    @mock.patch("index_core.files.store_files_to_disk")
    def test_store_files_disk_storage(self, mock_store_disk):
        """Test store_files falls back to disk storage when AWS not configured."""
        test_data = b"Test data"
        filename = "test.txt"

        md5_hash, returned_filename = store_files(None, filename, test_data, "text/plain")

        # Should call disk storage
        mock_store_disk.assert_called_once_with(filename, test_data)

        # Should return MD5 and filename
        expected_md5 = hashlib.md5(test_data, usedforsecurity=False).hexdigest()
        self.assertEqual(md5_hash, expected_md5)
        self.assertEqual(returned_filename, filename)

    def test_store_files_to_disk_valid(self):
        """Test store_files_to_disk with valid input."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock os.getcwd to return temp directory
            with mock.patch("os.getcwd", return_value=temp_dir):
                test_data = b"Test file content"
                filename = "test_file.bin"

                # Store file
                store_files_to_disk(filename, test_data)

                # Verify file was created
                expected_path = os.path.join(temp_dir, "files", filename)
                self.assertTrue(os.path.exists(expected_path))

                # Verify content
                with open(expected_path, "rb") as f:
                    self.assertEqual(f.read(), test_data)

    def test_store_files_to_disk_none_data(self):
        """Test store_files_to_disk with None data."""
        # Should return early without error
        store_files_to_disk("test.txt", None)

    def test_store_files_to_disk_none_filename(self):
        """Test store_files_to_disk with None filename."""
        # Should return early without error
        store_files_to_disk(None, b"data")

    def test_store_files_to_disk_exception(self):
        """Test store_files_to_disk with write error."""
        with mock.patch("builtins.open", side_effect=IOError("Disk full")):
            with self.assertRaises(IOError) as context:
                store_files_to_disk("test.txt", b"data")
            self.assertEqual(str(context.exception), "Disk full")

    @mock.patch("index_core.files.config.STORE_FILES", True)
    @mock.patch("index_core.files.config.AWS_SECRET_ACCESS_KEY", "secret")
    @mock.patch("index_core.files.config.AWS_ACCESS_KEY_ID", "key")
    @mock.patch("index_core.files.config.AWS_S3_BUCKETNAME", "bucket")
    @mock.patch("index_core.files.config.AWS_S3_IMAGE_DIR", "images")
    @mock.patch("index_core.files.config.USE_ASYNC_UPLOADS", True)
    @mock.patch("index_core.files.async_check_existing_and_upload_to_s3")
    def test_store_files_async_aws(self, mock_async_upload):
        """Test store_files with async AWS upload."""
        test_data = b"Test data"
        filename = "test.txt"

        md5_hash, returned_filename = store_files(None, filename, test_data, "text/plain")

        # Should call async upload
        mock_async_upload.assert_called_once()

        # Check call arguments
        call_args = mock_async_upload.call_args[0]
        self.assertEqual(call_args[0], filename)
        self.assertEqual(call_args[1], "text/plain")
        self.assertIsInstance(call_args[2], io.BytesIO)
        self.assertEqual(call_args[3], md5_hash)

    @mock.patch("index_core.files.config.STORE_FILES", True)
    @mock.patch("index_core.files.config.AWS_SECRET_ACCESS_KEY", "secret")
    @mock.patch("index_core.files.config.AWS_ACCESS_KEY_ID", "key")
    @mock.patch("index_core.files.config.AWS_S3_BUCKETNAME", "bucket")
    @mock.patch("index_core.files.config.AWS_S3_IMAGE_DIR", "images")
    @mock.patch("index_core.files.config.USE_ASYNC_UPLOADS", False)
    @mock.patch("index_core.files.check_existing_and_upload_to_s3")
    def test_store_files_sync_aws(self, mock_sync_upload):
        """Test store_files with synchronous AWS upload."""
        test_data = b"Test data"
        filename = "test.txt"

        md5_hash, returned_filename = store_files(None, filename, test_data, "text/plain")

        # Should call sync upload
        mock_sync_upload.assert_called_once()

        # Check call arguments
        call_args = mock_sync_upload.call_args[0]
        self.assertIsNone(call_args[0])  # db
        self.assertEqual(call_args[1], filename)
        self.assertEqual(call_args[2], "text/plain")
        self.assertIsInstance(call_args[3], io.BytesIO)
        self.assertEqual(call_args[4], md5_hash)

    def test_store_files_to_disk_with_existing_directory(self):
        """Test store_files_to_disk when files directory already exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Pre-create the files directory
            files_dir = os.path.join(temp_dir, "files")
            os.makedirs(files_dir)

            with mock.patch("os.getcwd", return_value=temp_dir):
                test_data = b"Test file content"
                filename = "test_file.bin"

                # Store file - should not fail even though directory exists
                store_files_to_disk(filename, test_data)

                # Verify file was created
                expected_path = os.path.join(files_dir, filename)
                self.assertTrue(os.path.exists(expected_path))

    @mock.patch("index_core.files.logger")
    def test_get_fileobj_and_md5_none_input_logging(self, mock_logger):
        """Test that get_fileobj_and_md5 logs warning for None input."""
        file_obj, md5_hash = get_fileobj_and_md5(None)

        self.assertIsNone(file_obj)
        self.assertIsNone(md5_hash)
        mock_logger.warning.assert_called_once_with("decoded_base64 is None")

    @mock.patch("index_core.files.logger")
    def test_store_files_to_disk_none_data_logging(self, mock_logger):
        """Test that store_files_to_disk logs info for None data."""
        store_files_to_disk("test.txt", None)
        mock_logger.info.assert_called_once_with("decoded_base64 is None")

    @mock.patch("index_core.files.logger")
    def test_store_files_to_disk_none_filename_logging(self, mock_logger):
        """Test that store_files_to_disk logs info for None filename."""
        store_files_to_disk(None, b"data")
        mock_logger.info.assert_called_once_with("filename is None")

    def test_get_fileobj_and_md5_empty_data(self):
        """Test get_fileobj_and_md5 with empty byte string."""
        test_data = b""
        file_obj, md5_hash = get_fileobj_and_md5(test_data)

        # Should still work with empty data
        self.assertIsInstance(file_obj, io.BytesIO)
        file_obj.seek(0)
        self.assertEqual(file_obj.read(), b"")

        # MD5 of empty string
        expected_md5 = hashlib.md5(b"", usedforsecurity=False).hexdigest()
        self.assertEqual(md5_hash, expected_md5)


if __name__ == "__main__":
    unittest.main()
