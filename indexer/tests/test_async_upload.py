"""
Test script for the async upload functionality.

This script tests the asynchronous file upload capabilities by simulating
multiple file uploads and verifying they are processed correctly.
"""

import base64
import io
import logging
import os
import sys
import threading
import time
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True, scope="module")
def module_isolation():
    """Provide comprehensive isolation for this module."""
    from tests.test_isolation_utils import TestIsolationManager

    modules_to_mock = ["boto3", "pymysql", "pymysql.connections", "pymysql.cursors"]

    with TestIsolationManager().isolate_sys_modules(modules_to_mock).isolate_sys_path().isolate_logging():
        # Mock AWS and database modules before importing any other modules
        sys.modules["boto3"] = MagicMock()
        sys.modules["pymysql"] = MagicMock()
        sys.modules["pymysql.connections"] = MagicMock()
        sys.modules["pymysql.cursors"] = MagicMock()

        # Add the src directory to the Python path
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

        yield


# Now import our modules
import config
from index_core.async_upload import (
    UploadTask,
    _process_upload_task,
    async_check_existing_and_upload_to_s3,
    start_upload_worker,
    stop_upload_worker,
    wait_for_uploads,
)


def create_test_file(size_kb=10, content=None):
    """Create a test file with random content."""
    if content:
        data = content.encode("utf-8")
    else:
        # Generate random data
        data = os.urandom(size_kb * 1024)

    # Create a file-like object
    file_obj = BytesIO(data)

    # Calculate MD5 hash
    import hashlib

    file_obj.seek(0)
    file_obj_md5 = hashlib.md5(file_obj.read(), usedforsecurity=False).hexdigest()
    file_obj.seek(0)

    return file_obj, file_obj_md5


def test_upload_task_processing():
    """Test the processing of an upload task directly."""
    logger.info("Testing upload task processing...")

    # Create a test file
    file_obj, file_obj_md5 = create_test_file(content="Test file content")
    filename = "test_file.txt"
    mime_type = "text/plain"

    # Create an upload task
    task = UploadTask(filename, mime_type, file_obj, file_obj_md5)

    # Create mock functions
    mock_upload = MagicMock(return_value=True)
    mock_update_db = MagicMock(return_value=True)
    mock_db = MagicMock()

    # Patch the necessary functions at the correct locations
    with patch("index_core.async_upload.DatabaseManager") as mock_db_mgr_cls:
        mock_db_mgr_instance = MagicMock()
        mock_db_mgr_instance.connect.return_value = mock_db
        mock_db_mgr_cls.return_value = mock_db_mgr_instance
        with patch("index_core.async_upload.upload_file_to_s3", mock_upload):
            with patch("index_core.async_upload.update_s3_db_objects", mock_update_db):
                # Process the task
                _process_upload_task(task)

                # Verify the functions were called
                mock_upload.assert_called_once()
                mock_update_db.assert_called_once()

                logger.info("Upload task processing test passed!")


def test_async_upload_single_file():
    """Test uploading a single file asynchronously."""
    logger.info("Testing single file async upload...")

    # Create a test file
    file_obj, file_obj_md5 = create_test_file(content="Test file content")
    filename = "test_file.txt"
    mime_type = "text/plain"

    # Create an event to track when upload_file_to_s3 is called
    upload_called_event = threading.Event()
    update_db_called_event = threading.Event()

    # Create mock functions that set events when called
    def mock_upload(*args, **kwargs):
        logger.debug("Mock upload_file_to_s3 called")
        upload_called_event.set()
        return True

    def mock_update_db(*args, **kwargs):
        logger.debug("Mock update_s3_db_objects called")
        update_db_called_event.set()
        return True

    # Create a mock database connection
    mock_db = MagicMock()

    # Patch the necessary functions at the correct locations
    with patch("index_core.async_upload.DatabaseManager") as mock_db_mgr_cls:
        mock_db_mgr_instance = MagicMock()
        mock_db_mgr_instance.connect.return_value = mock_db
        mock_db_mgr_cls.return_value = mock_db_mgr_instance
        with patch("index_core.async_upload.upload_file_to_s3", side_effect=mock_upload):
            with patch("index_core.async_upload.update_s3_db_objects", side_effect=mock_update_db):

                # Start the upload worker
                start_upload_worker()

                try:
                    # Queue the file for upload
                    async_check_existing_and_upload_to_s3(filename, mime_type, file_obj, file_obj_md5)

                    # Wait for the upload to be called (with timeout)
                    logger.info("Waiting for upload to be called...")
                    if not upload_called_event.wait(timeout=5.0):
                        logger.error("Timed out waiting for upload_file_to_s3 to be called")
                        assert False, "upload_file_to_s3 was not called within timeout"

                    # Wait for the update_db to be called (with timeout)
                    logger.info("Waiting for update_db to be called...")
                    if not update_db_called_event.wait(timeout=5.0):
                        logger.error("Timed out waiting for update_s3_db_objects to be called")
                        assert False, "update_s3_db_objects was not called within timeout"

                    logger.info("Single file async upload test passed!")
                finally:
                    # Stop the upload worker
                    stop_upload_worker()


def test_async_upload_with_existing_file():
    """Test uploading a file that already exists in S3."""
    logger.info("Testing async upload with existing file...")

    # Create a test file
    file_obj, file_obj_md5 = create_test_file(content="Test file content")
    filename = "existing_file.txt"
    mime_type = "text/plain"
    s3_file_path = f"{config.AWS_S3_IMAGE_DIR}{filename}"

    # Mock the S3_OBJECTS dictionary to simulate an existing file
    config.S3_OBJECTS = {s3_file_path: {"md5": file_obj_md5}}

    # Create events to track function calls
    upload_called_event = threading.Event()
    update_db_called_event = threading.Event()

    # Create mock functions that set events when called
    def mock_upload(*args, **kwargs):
        logger.debug("Mock upload_file_to_s3 called - THIS SHOULD NOT HAPPEN")
        upload_called_event.set()
        return True

    def mock_update_db(*args, **kwargs):
        logger.debug("Mock update_s3_db_objects called - THIS SHOULD NOT HAPPEN")
        update_db_called_event.set()
        return True

    # Create a mock database connection
    mock_db = MagicMock()

    # Patch the necessary functions at the correct locations
    with patch("index_core.async_upload.DatabaseManager") as mock_db_mgr_cls:
        mock_db_mgr_instance = MagicMock()
        mock_db_mgr_instance.connect.return_value = mock_db
        mock_db_mgr_cls.return_value = mock_db_mgr_instance
        with patch("index_core.async_upload.upload_file_to_s3", side_effect=mock_upload):
            with patch("index_core.async_upload.update_s3_db_objects", side_effect=mock_update_db):

                # Start the upload worker
                start_upload_worker()

                try:
                    # Queue the file for upload
                    async_check_existing_and_upload_to_s3(filename, mime_type, file_obj, file_obj_md5)

                    # Wait a bit to ensure the worker has time to process the task
                    time.sleep(1.0)

                    # Verify that the upload and update_db functions were NOT called
                    assert not upload_called_event.is_set(), "upload_file_to_s3 was called but should not have been"
                    assert not update_db_called_event.is_set(), "update_s3_db_objects was called but should not have been"

                    logger.info("Async upload with existing file test passed!")
                finally:
                    # Stop the upload worker
                    stop_upload_worker()

                    # Reset S3_OBJECTS
                    config.S3_OBJECTS = {}


def main():
    """Run all tests."""
    logger.info("Starting async upload tests...")

    # Initialize config attributes
    config.AWS_S3_IMAGE_DIR = "test/"
    config.AWS_S3_BUCKETNAME = "test-bucket"
    config.AWS_S3_CLIENT = MagicMock()
    config.S3_OBJECTS = {}
    config.AWS_CLOUDFRONT_DISTRIBUTION_ID = None
    config.AWS_INVALIDATE_CACHE = False

    # Run the tests
    test_upload_task_processing()
    test_async_upload_single_file()
    test_async_upload_with_existing_file()

    logger.info("All async upload tests completed successfully!")


if __name__ == "__main__":
    main()
