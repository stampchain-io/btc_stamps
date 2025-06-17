"""
Comprehensive test suite for AWS S3 and CloudFront integration.
Tests cover all functions in index_core/aws.py with proper mocking.
"""

import hashlib
import logging
from io import BytesIO
from unittest.mock import MagicMock, Mock, call, patch

import pytest

# Import the module to test
from index_core import aws


class TestAWSIntegration:
    """Test suite for AWS S3 and CloudFront operations."""

    @pytest.fixture
    def mock_db(self):
        """Mock database connection."""
        db = Mock()
        cursor = Mock()
        db.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = None
        return db

    @pytest.fixture
    def mock_s3_client(self):
        """Mock S3 client."""
        return Mock()

    @pytest.fixture
    def mock_config(self):
        """Mock config module."""
        with patch("index_core.aws.config") as mock:
            mock.AWS_S3_IMAGE_DIR = "stamps/"
            mock.AWS_S3_BUCKETNAME = "test-bucket"
            mock.AWS_CLOUDFRONT_DISTRIBUTION_ID = "ABCD1234"
            mock.AWS_INVALIDATE_CACHE = True
            mock.S3_OBJECTS = {}
            mock.AWS_S3_CLIENT = Mock()
            yield mock

    def test_get_s3_objects_from_database(self, mock_db, mock_s3_client, mock_config):
        """Test retrieving S3 objects from database cache."""
        # Setup
        cursor = mock_db.cursor.return_value
        cursor.fetchall.return_value = [("stamps/file1.png", "abc123"), ("stamps/file2.jpg", "def456")]

        # Execute
        result = aws.get_s3_objects(mock_db, "test-bucket", mock_s3_client)

        # Assert
        assert len(result) == 2
        assert "stamps/file1.png" in result
        assert result["stamps/file1.png"]["md5"] == "abc123"
        assert result["stamps/file2.jpg"]["md5"] == "def456"

        # Verify database was queried
        cursor.execute.assert_called_once_with("SELECT path_key, md5 FROM s3objects")
        cursor.close.assert_called_once()

    def test_get_s3_objects_from_s3_when_db_empty(self, mock_db, mock_s3_client, mock_config):
        """Test fetching S3 objects from AWS when database is empty."""
        # Setup
        cursor = mock_db.cursor.return_value
        cursor.fetchall.return_value = []

        # Mock paginator
        paginator = Mock()
        mock_s3_client.get_paginator.return_value = paginator

        # Mock S3 response pages
        pages = [
            {"Contents": [{"Key": "stamps/file1.png", "ETag": '"abc123"'}, {"Key": "stamps/file2.jpg", "ETag": '"def456"'}]},
            {"Contents": [{"Key": "stamps/file3.gif", "ETag": '"ghi789"'}]},
        ]
        paginator.paginate.return_value = pages

        # Execute
        with patch("index_core.aws.add_s3_objects_to_db") as mock_add:
            result = aws.get_s3_objects(mock_db, "test-bucket", mock_s3_client)

        # Assert
        assert len(result) == 3
        assert result["stamps/file1.png"]["md5"] == "abc123"
        assert result["stamps/file3.gif"]["md5"] == "ghi789"

        # Verify S3 was queried
        mock_s3_client.get_paginator.assert_called_once_with("list_objects_v2")
        paginator.paginate.assert_called_once()

        # Verify objects were added to database
        mock_add.assert_called_once()
        added_objects = mock_add.call_args[0][1]
        assert len(added_objects) == 3

    def test_get_s3_objects_handles_missing_contents(self, mock_db, mock_s3_client, mock_config):
        """Test handling S3 pages without Contents key."""
        # Setup
        cursor = mock_db.cursor.return_value
        cursor.fetchall.return_value = []

        paginator = Mock()
        mock_s3_client.get_paginator.return_value = paginator

        # Page without Contents key
        pages = [{}, {"Contents": [{"Key": "stamps/file1.png", "ETag": '"abc123"'}]}]  # Empty page
        paginator.paginate.return_value = pages

        # Execute
        with patch("index_core.aws.add_s3_objects_to_db"):
            result = aws.get_s3_objects(mock_db, "test-bucket", mock_s3_client)

        # Assert only one object found
        assert len(result) == 1
        assert "stamps/file1.png" in result

    def test_update_s3_db_objects_new_file(self, mock_db, mock_config):
        """Test updating database with new S3 object."""
        # Setup
        cursor = mock_db.cursor.return_value
        cursor.fetchone.return_value = None  # No existing file

        # Execute
        aws.update_s3_db_objects(mock_db, "newfile.png", "xyz789")

        # Assert
        expected_path = "stamps/newfile.png"
        expected_id = f"{expected_path}_xyz789"

        # Verify database operations
        cursor.execute.assert_any_call("SELECT id FROM s3objects WHERE path_key = %s", (expected_path,))
        cursor.execute.assert_any_call(
            "INSERT IGNORE INTO s3objects (id, path_key, md5) VALUES (%s, %s, %s)", (expected_id, expected_path, "xyz789")
        )
        cursor.close.assert_called_once()

    def test_update_s3_db_objects_existing_file(self, mock_db, mock_config):
        """Test updating database when file already exists."""
        # Setup
        cursor = mock_db.cursor.return_value
        cursor.fetchone.return_value = ("old_id_123",)  # Existing file

        # Execute
        aws.update_s3_db_objects(mock_db, "existingfile.png", "newhash")

        # Assert
        # Verify old entry was deleted
        cursor.execute.assert_any_call("DELETE FROM s3objects WHERE id = %s", ("old_id_123",))

        # Verify new entry was inserted
        expected_path = "stamps/existingfile.png"
        cursor.execute.assert_any_call(
            "INSERT IGNORE INTO s3objects (id, path_key, md5) VALUES (%s, %s, %s)",
            (f"{expected_path}_newhash", expected_path, "newhash"),
        )

    def test_update_s3_db_objects_handles_exception(self, mock_db, mock_config, caplog):
        """Test error handling in update_s3_db_objects."""
        # Setup
        mock_db.cursor.side_effect = Exception("Database error")

        # Execute
        with caplog.at_level(logging.WARNING):
            aws.update_s3_db_objects(mock_db, "file.png", "hash123")

        # Assert
        assert "ERROR: Unable to update the s3objects table" in caplog.text
        assert "Database error" in caplog.text

    def test_add_s3_objects_to_db_success(self, mock_db, mock_config):
        """Test bulk adding S3 objects to database."""
        # Setup
        cursor = mock_db.cursor.return_value
        s3_objects = {
            "stamps/file1.png": {"md5": "hash1"},
            "stamps/file2.jpg": {"md5": "hash2"},
            "stamps/file3.gif": {"md5": "hash3"},
        }

        # Execute
        aws.add_s3_objects_to_db(mock_db, s3_objects)

        # Assert
        expected_values = [
            ("stamps/file1.pnghash1", "stamps/file1.png", "hash1"),
            ("stamps/file2.jpghash2", "stamps/file2.jpg", "hash2"),
            ("stamps/file3.gifhash3", "stamps/file3.gif", "hash3"),
        ]

        cursor.executemany.assert_called_once()
        query, values = cursor.executemany.call_args[0]
        assert query == "INSERT IGNORE INTO s3objects (id, path_key, md5) VALUES (%s, %s, %s)"
        # Sort values for comparison since dict ordering might vary
        assert sorted(values) == sorted(expected_values)

    def test_add_s3_objects_to_db_handles_exception(self, mock_db, mock_config, caplog):
        """Test error handling in add_s3_objects_to_db."""
        # Setup
        mock_db.cursor.side_effect = Exception("Bulk insert error")

        # Execute
        with caplog.at_level(logging.WARNING):
            aws.add_s3_objects_to_db(mock_db, {"file": {"md5": "hash"}})

        # Assert
        assert "ERROR: Unable to add S3 objects to the database" in caplog.text

    @patch("index_core.aws.boto3.client")
    def test_invalidate_s3_files(self, mock_boto_client, mock_config):
        """Test CloudFront invalidation."""
        # Setup
        mock_cloudfront = Mock()
        mock_boto_client.return_value = mock_cloudfront

        file_paths = ["/stamps/file1.png", "/stamps/file2.jpg"]
        distribution_id = "ABCD1234"

        # Execute
        response = aws.invalidate_s3_files(file_paths, distribution_id)

        # Assert
        mock_boto_client.assert_called_once_with("cloudfront")
        mock_cloudfront.create_invalidation.assert_called_once()

        # Verify invalidation batch
        call_args = mock_cloudfront.create_invalidation.call_args[1]
        assert call_args["DistributionId"] == distribution_id
        assert call_args["InvalidationBatch"]["Paths"]["Quantity"] == 2
        assert call_args["InvalidationBatch"]["Paths"]["Items"] == file_paths

    def test_upload_file_to_s3_with_file_object(self, mock_s3_client):
        """Test uploading file object to S3."""
        # Setup
        file_obj = BytesIO(b"test content")

        # Execute
        aws.upload_file_to_s3(file_obj, "test-bucket", "stamps/test.png", mock_s3_client, content_type="image/png")

        # Assert
        mock_s3_client.upload_fileobj.assert_called_once()
        args = mock_s3_client.upload_fileobj.call_args[0]
        assert args[0] == file_obj
        assert args[1] == "test-bucket"
        assert args[2] == "stamps/test.png"

        # Verify ExtraArgs
        kwargs = mock_s3_client.upload_fileobj.call_args[1]
        assert kwargs["ExtraArgs"]["ContentType"] == "image/png"

    def test_upload_file_to_s3_with_file_path(self, mock_s3_client):
        """Test uploading file from path to S3."""
        # Execute
        aws.upload_file_to_s3("/path/to/file.png", "test-bucket", "stamps/file.png", mock_s3_client)

        # Assert
        mock_s3_client.upload_file.assert_called_once_with(
            "/path/to/file.png", "test-bucket", "stamps/file.png", ExtraArgs={"ContentType": "binary/octet-stream"}
        )

    def test_upload_file_to_s3_handles_exception(self, mock_s3_client, caplog):
        """Test error handling in upload_file_to_s3."""
        # Setup
        mock_s3_client.upload_file.side_effect = Exception("Upload failed")

        # Execute
        with caplog.at_level(logging.WARNING):
            aws.upload_file_to_s3("/path/to/file.png", "test-bucket", "stamps/file.png", mock_s3_client)

        # Assert
        assert "failure uploading to aws" in caplog.text

    def test_check_existing_and_upload_new_file(self, mock_db, mock_config):
        """Test uploading new file that doesn't exist in S3."""
        # Setup
        file_obj = BytesIO(b"new file content")
        mock_config.S3_OBJECTS = {}  # Empty, file doesn't exist

        # Execute
        with patch("index_core.aws.upload_file_to_s3") as mock_upload, patch(
            "index_core.aws.update_s3_db_objects"
        ) as mock_update:
            aws.check_existing_and_upload_to_s3(mock_db, "newfile.png", "image/png", file_obj, "newhash123")

        # Assert
        mock_upload.assert_called_once()
        mock_update.assert_called_once_with(mock_db, "newfile.png", "newhash123")

    def test_check_existing_and_upload_same_hash(self, mock_db, mock_config, caplog):
        """Test skipping upload when file exists with same hash."""
        # Setup
        file_obj = BytesIO(b"content")
        mock_config.S3_OBJECTS = {"stamps/samefile.png": {"md5": "samehash"}}

        # Execute
        with patch("index_core.aws.upload_file_to_s3") as mock_upload:
            with caplog.at_level(logging.DEBUG):
                aws.check_existing_and_upload_to_s3(mock_db, "samefile.png", "image/png", file_obj, "samehash")

        # Assert
        mock_upload.assert_not_called()
        assert "already exists in S3. Skipping upload" in caplog.text

    def test_check_existing_and_upload_different_hash_with_invalidation(self, mock_db, mock_config):
        """Test uploading file with different hash and CloudFront invalidation."""
        # Setup
        file_obj = BytesIO(b"updated content")
        mock_config.S3_OBJECTS = {"stamps/updated.png": {"md5": "oldhash"}}
        mock_config.AWS_CLOUDFRONT_DISTRIBUTION_ID = "DIST123"
        mock_config.AWS_INVALIDATE_CACHE = True

        # Execute
        with patch("index_core.aws.upload_file_to_s3") as mock_upload, patch(
            "index_core.aws.update_s3_db_objects"
        ) as mock_update, patch("index_core.aws.invalidate_with_retries") as mock_invalidate:
            aws.check_existing_and_upload_to_s3(mock_db, "updated.png", "image/png", file_obj, "newhash")

        # Assert
        mock_upload.assert_called_once()
        mock_update.assert_called_once_with(mock_db, "updated.png", "newhash")
        mock_invalidate.assert_called_once_with("stamps/updated.png", "DIST123")

    @patch("index_core.aws.invalidate_s3_files")
    @patch("index_core.aws.time.sleep")
    def test_invalidate_with_retries_success(self, mock_sleep, mock_invalidate, mock_config):
        """Test successful CloudFront invalidation."""
        # Execute
        aws.invalidate_with_retries("stamps/test.png", "DIST123")

        # Assert
        mock_invalidate.assert_called_once_with(["/stamps/test.png"], "DIST123")
        mock_sleep.assert_not_called()

    @patch("index_core.aws.invalidate_s3_files")
    @patch("index_core.aws.time.sleep")
    def test_invalidate_with_retries_with_failures(self, mock_sleep, mock_invalidate, mock_config, caplog):
        """Test CloudFront invalidation with retries."""
        # Setup - fail twice, then succeed
        mock_invalidate.side_effect = [Exception("Network error"), Exception("Throttled"), None]  # Success on third try

        # Execute
        with caplog.at_level(logging.WARNING):
            aws.invalidate_with_retries("stamps/test.png", "DIST123")

        # Assert
        assert mock_invalidate.call_count == 3
        assert mock_sleep.call_count == 2
        assert "RETRYING" in caplog.text
        assert "Retry failed" in caplog.text

    @patch("index_core.aws.invalidate_s3_files")
    @patch("index_core.aws.time.sleep")
    def test_invalidate_with_retries_max_retries_reached(self, mock_sleep, mock_invalidate, mock_config, caplog):
        """Test CloudFront invalidation reaching max retries."""
        # Setup - always fail
        mock_invalidate.side_effect = Exception("Persistent error")

        # Execute
        with caplog.at_level(logging.WARNING):
            aws.invalidate_with_retries("stamps/test.png", "DIST123")

        # Assert
        assert mock_invalidate.call_count == 6  # Initial + 5 retries
        assert mock_sleep.call_count == 5
        assert "Maximum retries reached" in caplog.text

    def test_check_existing_and_upload_handles_upload_exception(self, mock_db, mock_config, caplog):
        """Test error handling during upload."""
        # Setup
        file_obj = BytesIO(b"content")
        mock_config.S3_OBJECTS = {}

        # Execute
        with patch("index_core.aws.upload_file_to_s3") as mock_upload:
            mock_upload.side_effect = Exception("S3 error")
            with caplog.at_level(logging.WARNING):
                aws.check_existing_and_upload_to_s3(mock_db, "error.png", "image/png", file_obj, "hash123")

        # Assert
        assert "ERROR: Unable to upload error.png to S3" in caplog.text

    def test_check_existing_and_upload_null_mime_type(self, mock_db, mock_config):
        """Test handling null mime type."""
        # Setup
        file_obj = BytesIO(b"content")
        mock_config.S3_OBJECTS = {}

        # Execute
        with patch("index_core.aws.upload_file_to_s3") as mock_upload:
            aws.check_existing_and_upload_to_s3(mock_db, "file.bin", None, file_obj, "hash123")  # Null mime type

        # Assert
        call_args = mock_upload.call_args[1]
        assert call_args["content_type"] == "binary/octet-stream"


class TestAWSEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_get_s3_objects_empty_pages(self):
        """Test handling completely empty S3 response."""
        db = Mock()
        cursor = Mock()
        db.cursor.return_value = cursor
        cursor.fetchall.return_value = []

        s3_client = Mock()
        paginator = Mock()
        s3_client.get_paginator.return_value = paginator
        paginator.paginate.return_value = []  # No pages at all

        with patch("index_core.aws.config") as mock_config:
            mock_config.AWS_S3_IMAGE_DIR = "stamps/"
            with patch("index_core.aws.add_s3_objects_to_db"):
                result = aws.get_s3_objects(db, "bucket", s3_client)

        assert result == {}

    def test_file_object_seek_behavior(self):
        """Test file object seek is called correctly."""
        db = Mock()
        file_obj = Mock(spec=["read", "seek"])

        with patch("index_core.aws.config") as mock_config:
            mock_config.S3_OBJECTS = {}
            mock_config.AWS_S3_IMAGE_DIR = "stamps/"

            with patch("index_core.aws.upload_file_to_s3"):
                aws.check_existing_and_upload_to_s3(db, "test.png", "image/png", file_obj, "hash123")

        # Verify seek(0) was called to reset file position
        file_obj.seek.assert_called_with(0)
