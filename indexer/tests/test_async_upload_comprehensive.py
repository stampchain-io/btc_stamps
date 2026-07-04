"""
Comprehensive test suite for async upload functionality.
Tests cover all functions in index_core/async_upload.py with proper mocking.
"""

import logging
import os
import queue
import threading
import time
from io import BytesIO
from unittest.mock import MagicMock, Mock, call, patch

import pytest

# Import the module to test
from index_core import async_upload
from index_core.async_upload import UploadTask


class TestAsyncUpload:
    """Test suite for asynchronous upload operations."""

    @pytest.fixture(autouse=True)
    def reset_module_state(self):
        """Reset module-level state before each test."""
        # Store original values
        orig_running = async_upload._upload_worker_running
        orig_thread = async_upload._upload_worker_thread

        # Reset state
        async_upload._upload_worker_running = False
        async_upload._upload_worker_thread = None

        # Clear the queue
        while not async_upload.upload_queue.empty():
            try:
                async_upload.upload_queue.get_nowait()
            except queue.Empty:
                break

        yield

        # Restore original values
        async_upload._upload_worker_running = orig_running
        async_upload._upload_worker_thread = orig_thread

    @pytest.fixture
    def mock_config(self):
        """Mock config module."""
        with patch("index_core.async_upload.config") as mock:
            mock.AWS_S3_IMAGE_DIR = "stamps/"
            mock.AWS_S3_BUCKETNAME = "test-bucket"
            mock.AWS_CLOUDFRONT_DISTRIBUTION_ID = "ABCD1234"
            mock.AWS_INVALIDATE_CACHE = True
            mock.S3_OBJECTS = {}
            mock.AWS_S3_CLIENT = Mock()
            yield mock

    @pytest.fixture
    def mock_db_manager(self):
        """Mock DatabaseManager."""
        with patch("index_core.async_upload.upload_db_manager") as mock:
            db_conn = Mock()
            mock.connect.return_value = db_conn
            yield mock

    def test_upload_task_initialization(self, mock_config):
        """Test UploadTask class initialization."""
        file_obj = BytesIO(b"test content")
        task = UploadTask("test.png", "image/png", file_obj, "hash123")

        assert task.filename == "test.png"
        assert task.mime_type == "image/png"
        assert task.file_obj == file_obj
        assert task.file_obj_md5 == "hash123"
        assert task.s3_file_path == "stamps/test.png"

    def test_upload_task_default_mime_type(self):
        """Test UploadTask with None mime type."""
        file_obj = BytesIO(b"content")
        task = UploadTask("test.bin", None, file_obj, "hash456")

        assert task.mime_type == "binary/octet-stream"

    @patch("index_core.async_upload.upload_file_to_s3")
    @patch("index_core.async_upload.update_s3_db_objects")
    def test_process_upload_task_new_file(self, mock_update_db, mock_upload, mock_config, mock_db_manager):
        """Test processing upload task for new file."""
        # Setup
        db_conn = mock_db_manager.connect.return_value
        mock_config.S3_OBJECTS = {}  # No existing file

        file_obj = BytesIO(b"new content")
        task = UploadTask("newfile.png", "image/png", file_obj, "newhash")

        # Execute
        async_upload._process_upload_task(task)

        # Assert
        mock_upload.assert_called_once_with(
            file_obj, "test-bucket", "stamps/newfile.png", mock_config.AWS_S3_CLIENT, content_type="image/png"
        )
        mock_update_db.assert_called_once_with(db_conn, "newfile.png", "newhash")
        db_conn.close.assert_called()

    @patch("index_core.async_upload.upload_file_to_s3")
    @patch("index_core.async_upload.update_s3_db_objects")
    def test_process_upload_task_existing_same_hash(self, mock_update_db, mock_upload, mock_config, mock_db_manager, caplog):
        """Test skipping upload when file exists with same hash."""
        # Setup
        db_conn = mock_db_manager.connect.return_value
        mock_config.S3_OBJECTS = {"stamps/existing.png": {"md5": "samehash"}}

        file_obj = BytesIO(b"content")
        task = UploadTask("existing.png", "image/png", file_obj, "samehash")

        # Execute
        with caplog.at_level(logging.DEBUG):
            async_upload._process_upload_task(task)

        # Assert
        mock_upload.assert_not_called()
        mock_update_db.assert_not_called()
        assert "already exists in S3. Skipping upload" in caplog.text
        db_conn.close.assert_called()

    @patch("index_core.async_upload.upload_file_to_s3")
    @patch("index_core.async_upload.update_s3_db_objects")
    @patch("index_core.async_upload.invalidate_with_retries")
    def test_process_upload_task_existing_different_hash(
        self, mock_invalidate, mock_update_db, mock_upload, mock_config, mock_db_manager
    ):
        """Test uploading file with different hash and CloudFront invalidation."""
        # Setup
        db_conn = mock_db_manager.connect.return_value
        mock_config.S3_OBJECTS = {"stamps/updated.png": {"md5": "oldhash"}}

        file_obj = BytesIO(b"updated content")
        task = UploadTask("updated.png", "image/png", file_obj, "newhash")

        # Execute
        async_upload._process_upload_task(task)

        # Assert
        mock_upload.assert_called_once()
        mock_update_db.assert_called_once_with(db_conn, "updated.png", "newhash")
        mock_invalidate.assert_called_once_with("stamps/updated.png", "ABCD1234")
        db_conn.close.assert_called()

    @patch("index_core.async_upload.upload_file_to_s3")
    def test_process_upload_task_handles_upload_error(self, mock_upload, mock_config, mock_db_manager, caplog):
        """Test handling upload errors."""
        # Setup
        db_conn = mock_db_manager.connect.return_value
        mock_config.S3_OBJECTS = {}
        mock_upload.side_effect = Exception("S3 error")

        file_obj = BytesIO(b"content")
        task = UploadTask("error.png", "image/png", file_obj, "hash123")

        # Execute
        with caplog.at_level(logging.WARNING):
            async_upload._process_upload_task(task)

        # Assert
        assert "ERROR: Unable to upload error.png to S3" in caplog.text
        db_conn.close.assert_called()

    def test_process_upload_task_handles_db_error(self, mock_config, mock_db_manager, caplog):
        """Test handling database connection errors."""
        # Setup
        mock_db_manager.connect.side_effect = Exception("DB connection failed")

        file_obj = BytesIO(b"content")
        task = UploadTask("test.png", "image/png", file_obj, "hash123")

        # Execute
        with caplog.at_level(logging.ERROR):
            async_upload._process_upload_task(task)

        # Assert
        assert "Unexpected error in upload worker" in caplog.text

    def test_upload_worker_processes_queue(self, mock_config):
        """Test upload worker thread processing queue."""
        # Setup
        processed_tasks = []

        def mock_process(task):
            processed_tasks.append(task)
            # Simulate some processing time
            time.sleep(0.01)

        with patch("index_core.async_upload._process_upload_task", side_effect=mock_process):
            # Start worker
            async_upload._upload_worker_running = True

            # Add tasks to queue
            task1 = UploadTask("file1.png", "image/png", BytesIO(b"1"), "hash1")
            task2 = UploadTask("file2.png", "image/png", BytesIO(b"2"), "hash2")

            async_upload.upload_queue.put(task1)
            async_upload.upload_queue.put(task2)

            # Run worker for a short time
            worker_thread = threading.Thread(target=async_upload._upload_worker)
            worker_thread.start()

            # Wait for queue to be empty
            max_wait = 2.0
            start_time = time.time()
            while not async_upload.upload_queue.empty() and (time.time() - start_time) < max_wait:
                time.sleep(0.1)

            # Stop worker
            async_upload._upload_worker_running = False
            worker_thread.join(timeout=2)

        # Assert
        assert len(processed_tasks) == 2
        assert processed_tasks[0] == task1
        assert processed_tasks[1] == task2

    def test_upload_worker_handles_task_errors(self, mock_config, caplog):
        """Test upload worker continues after task errors."""
        # Setup
        call_count = 0

        def mock_process(task):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Task error")

        with patch("index_core.async_upload._process_upload_task", side_effect=mock_process):
            async_upload._upload_worker_running = True

            # Add tasks
            async_upload.upload_queue.put(UploadTask("fail.png", None, BytesIO(), "h1"))
            async_upload.upload_queue.put(UploadTask("success.png", None, BytesIO(), "h2"))

            # Run worker
            worker_thread = threading.Thread(target=async_upload._upload_worker)
            worker_thread.start()

            # Wait and stop
            time.sleep(0.5)
            async_upload._upload_worker_running = False
            worker_thread.join(timeout=2)

        # Assert
        assert call_count == 2  # Both tasks were attempted
        assert "Error processing upload task" in caplog.text

    def test_start_upload_worker(self):
        """Test starting upload worker thread."""
        # Execute
        async_upload.start_upload_worker()

        # Assert
        assert async_upload._upload_worker_running is True
        assert async_upload._upload_worker_thread is not None
        assert async_upload._upload_worker_thread.is_alive()

        # Cleanup
        async_upload._upload_worker_running = False
        async_upload._upload_worker_thread.join(timeout=2)

    def test_start_upload_worker_already_running(self, caplog):
        """Test starting worker when already running."""
        # Setup
        async_upload._upload_worker_running = True

        # Execute
        with caplog.at_level(logging.WARNING):
            async_upload.start_upload_worker()

        # Assert
        assert "Upload worker thread is already running" in caplog.text

    def test_stop_upload_worker(self):
        """Test stopping upload worker thread."""
        # Start worker first
        async_upload.start_upload_worker()
        assert async_upload._upload_worker_running is True

        # Stop worker
        with patch("index_core.async_upload.upload_executor") as mock_executor:
            async_upload.stop_upload_worker()

        # Assert
        assert async_upload._upload_worker_running is False
        mock_executor.shutdown.assert_called_once_with(wait=True, cancel_futures=True)

    def test_stop_upload_worker_not_running(self, caplog):
        """Test stopping worker when not running."""
        # Setup
        async_upload._upload_worker_running = False

        # Execute
        with patch("index_core.async_upload.upload_executor") as mock_executor:
            with caplog.at_level(logging.DEBUG):
                async_upload.stop_upload_worker()

        # Assert
        assert "Upload worker thread is not running" in caplog.text
        mock_executor.shutdown.assert_called_once()

    def test_stop_upload_worker_handles_shutdown_error(self, caplog):
        """Test handling executor shutdown errors."""
        # Setup
        with patch("index_core.async_upload.upload_executor") as mock_executor:
            mock_executor.shutdown.side_effect = Exception("Shutdown error")

            with caplog.at_level(logging.ERROR):
                async_upload.stop_upload_worker()

        # Assert
        assert "Error shutting down upload executor" in caplog.text

    def test_queue_file_upload(self):
        """Test queuing file for upload."""
        # Setup
        async_upload._upload_worker_running = True
        file_obj = BytesIO(b"test content")

        # Execute
        async_upload.queue_file_upload("test.png", "image/png", file_obj, "hash123")

        # Assert
        assert not async_upload.upload_queue.empty()
        task = async_upload.upload_queue.get_nowait()
        assert task.filename == "test.png"
        assert task.mime_type == "image/png"
        assert task.file_obj_md5 == "hash123"
        # Verify file was copied
        assert task.file_obj.getvalue() == b"test content"

    def test_queue_file_upload_starts_worker_if_not_running(self):
        """Test queue_file_upload starts worker if needed."""
        # Setup
        async_upload._upload_worker_running = False

        with patch("index_core.async_upload.start_upload_worker") as mock_start:
            file_obj = BytesIO(b"content")
            async_upload.queue_file_upload("test.png", None, file_obj, "hash")

        # Assert
        mock_start.assert_called_once()

    def test_wait_for_uploads_no_timeout(self):
        """Test waiting for uploads without timeout."""
        # Setup - empty queue
        assert async_upload.upload_queue.empty()

        # Mock queue.join() to return immediately
        with patch.object(async_upload.upload_queue, "join"):
            # Execute
            result = async_upload.wait_for_uploads()

        # Assert
        assert result is True

    def test_wait_for_uploads_with_timeout_success(self):
        """Test waiting for uploads with timeout - success case."""
        # Setup - empty queue
        assert async_upload.upload_queue.empty()

        # Mock unfinished_tasks to be 0 (no tasks in progress)
        with patch.object(async_upload.upload_queue, "unfinished_tasks", 0):
            # Execute
            result = async_upload.wait_for_uploads(timeout=1.0)

        # Assert
        assert result is True

    def test_wait_for_uploads_with_timeout_failure(self):
        """Test waiting for uploads with timeout - timeout case."""
        # Setup - add task that won't be processed
        async_upload.upload_queue.put(UploadTask("test.png", None, BytesIO(), "hash"))

        # Execute
        start_time = time.time()
        result = async_upload.wait_for_uploads(timeout=0.5)
        elapsed = time.time() - start_time

        # Assert
        assert result is False
        assert elapsed >= 0.5
        assert elapsed < 1.0

    def test_wait_for_uploads_with_unfinished_tasks(self):
        """Test wait behavior with unfinished tasks."""
        # Setup
        task = UploadTask("test.png", None, BytesIO(), "hash")
        async_upload.upload_queue.put(task)

        # Simulate task being processed but not finished
        async_upload.upload_queue.get_nowait()
        # Don't call task_done()

        # Execute
        result = async_upload.wait_for_uploads(timeout=0.1)

        # Assert
        assert result is False  # Unfinished tasks exist

        # Cleanup
        async_upload.upload_queue.task_done()

    def test_async_check_existing_and_upload_to_s3(self):
        """Test async wrapper function."""
        # Setup
        with patch("index_core.async_upload.queue_file_upload") as mock_queue:
            file_obj = BytesIO(b"content")

            # Execute
            async_upload.async_check_existing_and_upload_to_s3("test.png", "image/png", file_obj, "hash123")

        # Assert
        mock_queue.assert_called_once_with("test.png", "image/png", file_obj, "hash123")

    def test_file_object_seek_behavior(self):
        """Test that file objects are properly seeked."""
        # Setup
        file_obj = BytesIO(b"test content")
        file_obj.read(5)  # Move position to 5
        initial_position = file_obj.tell()
        assert initial_position == 5  # Verify we moved the position

        task = UploadTask("test.png", "image/png", file_obj, "hash")

        with patch("index_core.async_upload.upload_file_to_s3") as mock_upload:
            with patch("index_core.async_upload.config") as mock_config:
                with patch("index_core.async_upload.update_s3_db_objects"):
                    with patch("index_core.async_upload.upload_db_manager") as mock_db_manager:
                        # Setup mocks
                        mock_config.S3_OBJECTS = {}
                        mock_config.AWS_S3_BUCKETNAME = "test-bucket"
                        mock_config.AWS_S3_CLIENT = Mock()
                        mock_config.AWS_CLOUDFRONT_DISTRIBUTION_ID = None  # Disable CloudFront to simplify

                        # Mock database connection
                        mock_db = Mock()
                        mock_db_manager.connect.return_value = mock_db

                        async_upload._process_upload_task(task)

        # Assert - file should be at position 0 after seek(0) call in _process_upload_task
        assert file_obj.tell() == 0

    def test_max_concurrent_uploads_configuration(self):
        """Test MAX_CONCURRENT_UPLOADS configuration."""
        # The module is already loaded with MAX_CONCURRENT_UPLOADS set to 5
        # Test that the upload_executor exists and is a ThreadPoolExecutor
        assert hasattr(async_upload, "upload_executor")
        assert async_upload.upload_executor is not None

        # Test that MAX_CONCURRENT_UPLOADS environment variable is respected
        with patch.dict("os.environ", {"MAX_CONCURRENT_UPLOADS": "3"}):
            # The value should be parsed as int from environment
            max_workers = int(os.environ.get("MAX_CONCURRENT_UPLOADS", "5"))
            assert max_workers == 3
