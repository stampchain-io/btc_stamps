"""
Asynchronous file upload module for Bitcoin Stamps Indexer.

This module provides asynchronous file upload capabilities to AWS S3,
allowing the main indexer process to continue while files are uploaded
in the background.
"""

import logging
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Optional

import config
from index_core.aws import invalidate_with_retries, update_s3_db_objects, upload_file_to_s3
from index_core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)

# Maximum number of concurrent uploads
MAX_CONCURRENT_UPLOADS = int(os.environ.get("MAX_CONCURRENT_UPLOADS", "5"))

# Queue for pending uploads
upload_queue = queue.Queue()

# Thread pool for handling uploads
upload_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_UPLOADS)

# Dedicated database manager for file uploads
upload_db_manager = DatabaseManager()

# Flag to control the upload worker thread
_upload_worker_running = False
_upload_worker_thread = None


class UploadTask:
    """Represents a file upload task."""

    def __init__(self, filename: str, mime_type: str, file_obj: BytesIO, file_obj_md5: str):
        """
        Initialize an upload task.

        Args:
            filename: The name of the file to upload
            mime_type: The MIME type of the file
            file_obj: The file object to upload
            file_obj_md5: The MD5 hash of the file
        """
        self.filename = filename
        self.mime_type = mime_type or "binary/octet-stream"
        self.file_obj = file_obj
        self.file_obj_md5 = file_obj_md5
        self.s3_file_path = f"{config.AWS_S3_IMAGE_DIR}{filename}"


def _process_upload_task(task: UploadTask) -> None:
    """
    Process a single upload task.

    This function handles the actual upload to S3, database updates,
    and cache invalidation if needed.

    Args:
        task: The upload task to process
    """
    try:
        # Get a dedicated database connection for this upload
        db = upload_db_manager.connect()

        existing_obj = config.S3_OBJECTS.get(task.s3_file_path)

        if existing_obj and existing_obj["md5"] == task.file_obj_md5:
            logger.debug(f"File {task.filename} with hash {task.file_obj_md5} already exists in S3. Skipping upload.")
            db.close()
            return

        # If file exists but hash is different, or file doesn't exist
        try:
            task.file_obj.seek(0)
            if existing_obj:
                logger.debug(f"Uploading {task.filename} with changed hash {task.file_obj_md5} to S3...")
            else:
                logger.debug(f"Uploading new {task.filename} with hash {task.file_obj_md5} to S3...")

            upload_file_to_s3(
                task.file_obj,
                config.AWS_S3_BUCKETNAME,
                task.s3_file_path,
                config.AWS_S3_CLIENT,
                content_type=task.mime_type,
            )

            # Update database with new file information
            update_s3_db_objects(db, task.filename, task.file_obj_md5)

            # Invalidate CloudFront cache if needed
            if existing_obj and config.AWS_CLOUDFRONT_DISTRIBUTION_ID and config.AWS_INVALIDATE_CACHE:
                logger.debug(f"Invalidating {task.filename} with changed hash {task.file_obj_md5} in CloudFront...")
                invalidate_with_retries(task.s3_file_path, config.AWS_CLOUDFRONT_DISTRIBUTION_ID)

        except Exception as e:
            logger.warning(f"ERROR: Unable to upload {task.filename} to S3. Error: {e}")
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Unexpected error in upload worker: {e}", exc_info=True)


def _upload_worker() -> None:
    """
    Worker thread function that processes the upload queue.

    This function runs in a separate thread and continuously processes
    upload tasks from the queue until stopped.
    """
    global _upload_worker_running

    logger.info("Starting async upload worker thread")

    while _upload_worker_running:
        try:
            # Get a task from the queue with a timeout
            task = upload_queue.get(timeout=1.0)

            try:
                # Process the upload task
                _process_upload_task(task)
            except Exception as e:
                logger.error(f"Error processing upload task: {e}", exc_info=True)
            finally:
                # Mark the task as done
                upload_queue.task_done()

        except queue.Empty:
            # No tasks in the queue, continue waiting
            continue
        except Exception as e:
            logger.error(f"Unexpected error in upload worker: {e}", exc_info=True)

    logger.info("Async upload worker thread stopped")


def start_upload_worker() -> None:
    """
    Start the upload worker thread if it's not already running.

    This function should be called during application startup.
    """
    global _upload_worker_running, _upload_worker_thread

    if _upload_worker_running:
        logger.warning("Upload worker thread is already running")
        return

    _upload_worker_running = True
    _upload_worker_thread = threading.Thread(target=_upload_worker, daemon=True)
    _upload_worker_thread.start()

    logger.info("Async upload worker thread started")


def stop_upload_worker() -> None:
    """
    Stop the upload worker thread.

    This function should be called during application shutdown.
    """
    global _upload_worker_running, _upload_worker_thread

    if not _upload_worker_running:
        logger.warning("Upload worker thread is not running")
        return

    logger.info("Stopping async upload worker thread...")
    _upload_worker_running = False

    if _upload_worker_thread and _upload_worker_thread.is_alive():
        _upload_worker_thread.join(timeout=5.0)

    logger.info("Async upload worker thread stopped")


def queue_file_upload(filename: str, mime_type: str, file_obj: BytesIO, file_obj_md5: str) -> None:
    """
    Queue a file for asynchronous upload to S3.

    This function creates an upload task and adds it to the queue for
    processing by the upload worker thread.

    Args:
        filename: The name of the file to upload
        mime_type: The MIME type of the file
        file_obj: The file object to upload
        file_obj_md5: The MD5 hash of the file
    """
    if not _upload_worker_running:
        logger.warning("Upload worker thread is not running, starting it now")
        start_upload_worker()

    # Create a copy of the file object to avoid issues with concurrent access
    file_copy = BytesIO(file_obj.getvalue())

    # Create and queue the upload task
    task = UploadTask(filename, mime_type, file_copy, file_obj_md5)
    upload_queue.put(task)

    logger.debug(f"Queued file {filename} for async upload")


def wait_for_uploads(timeout: Optional[float] = None) -> bool:
    """
    Wait for all queued uploads to complete.

    This function blocks until all uploads in the queue have been processed
    or until the specified timeout is reached.

    Args:
        timeout: Maximum time to wait in seconds, or None to wait indefinitely

    Returns:
        True if all uploads completed, False if timeout was reached
    """
    if timeout is None:
        # Wait indefinitely
        upload_queue.join()
        return True
    else:
        # Wait with timeout
        end_time = time.time() + timeout

        # Check if the queue is empty or if we've timed out
        while not upload_queue.empty():
            if time.time() > end_time:
                return False

            # Wait for a short interval and check again
            time.sleep(0.1)

        # Queue is empty, but we need to make sure all tasks are done
        remaining_time = end_time - time.time()
        if remaining_time <= 0:
            return not upload_queue.unfinished_tasks

        # Wait for the remaining time
        time.sleep(min(remaining_time, 0.1))
        return not upload_queue.unfinished_tasks


def async_check_existing_and_upload_to_s3(filename: str, mime_type: str, file_obj: BytesIO, file_obj_md5: str) -> None:
    """
    Asynchronously check if a file exists in S3 and upload it if needed.

    This function is the async equivalent of check_existing_and_upload_to_s3
    and should be used as a drop-in replacement.

    Args:
        filename: The name of the file to upload
        mime_type: The MIME type of the file
        file_obj: The file object to upload
        file_obj_md5: The MD5 hash of the file
    """
    queue_file_upload(filename, mime_type, file_obj, file_obj_md5)
