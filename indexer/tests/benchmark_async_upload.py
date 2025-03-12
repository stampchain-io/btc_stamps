"""
Benchmark script to compare synchronous vs. asynchronous file uploads.

This script measures the performance difference between synchronous and
asynchronous file uploads to demonstrate the benefits of the async approach.
It uses the actual S3 endpoint for realistic benchmarking.
"""

import base64
import io
import logging
import os
import sys
import time
import uuid
from io import BytesIO
from typing import Dict, List, Tuple

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import our modules
import config
from index_core.async_upload import (
    async_check_existing_and_upload_to_s3,
    start_upload_worker,
    stop_upload_worker,
    wait_for_uploads,
)
from index_core.aws import check_existing_and_upload_to_s3
from index_core.database_manager import DatabaseManager

# Default benchmark parameters
DEFAULT_NUM_FILES = 10
DEFAULT_FILE_SIZE_KB = 50

# Simulated processing time between uploads (in seconds)
PROCESSING_TIME = 0.05


def create_test_file(size_kb, content=None):
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


def generate_unique_filename():
    """Generate a unique filename for testing."""
    return f"benchmark_test_{uuid.uuid4().hex}.dat"


def simulate_processing():
    """Simulate processing work that would happen between file uploads."""
    time.sleep(PROCESSING_TIME)


def benchmark_sync_uploads(db, num_files, file_size_kb):
    """Benchmark synchronous file uploads."""
    logger.info(f"Starting synchronous upload benchmark with {num_files} files of {file_size_kb}KB each...")

    # Create test files
    files = []
    for i in range(num_files):
        file_obj, file_obj_md5 = create_test_file(file_size_kb)
        filename = generate_unique_filename()
        mime_type = "application/octet-stream"
        files.append((filename, mime_type, file_obj, file_obj_md5))

    # Measure the time to upload all files synchronously
    start_time = time.time()

    # Process each file synchronously
    for i, (filename, mime_type, file_obj, file_obj_md5) in enumerate(files):
        check_existing_and_upload_to_s3(db, filename, mime_type, file_obj, file_obj_md5)

        # Simulate main thread work between uploads (e.g., processing transactions)
        logger.info(f"Main thread: Processed file {i+1}/{num_files} and continuing with other work...")
        simulate_processing()

    # Calculate total time
    total_time = time.time() - start_time

    logger.info(f"Synchronous upload benchmark completed in {total_time:.2f} seconds")
    return total_time


def benchmark_async_uploads(db, num_files, file_size_kb):
    """Benchmark asynchronous file uploads."""
    logger.info(f"Starting asynchronous upload benchmark with {num_files} files of {file_size_kb}KB each...")

    # Create test files
    files = []
    for i in range(num_files):
        file_obj, file_obj_md5 = create_test_file(file_size_kb)
        filename = generate_unique_filename()
        mime_type = "application/octet-stream"
        files.append((filename, mime_type, file_obj, file_obj_md5))

    # Start the upload worker
    start_upload_worker()

    try:
        # Measure the time to queue all files for async upload
        start_time = time.time()

        # Queue each file for async upload
        for i, (filename, mime_type, file_obj, file_obj_md5) in enumerate(files):
            async_check_existing_and_upload_to_s3(filename, mime_type, file_obj, file_obj_md5)

            # Simulate main thread work between uploads (e.g., processing transactions)
            logger.info(f"Main thread: Queued file {i+1}/{num_files} and immediately continuing with other work...")
            simulate_processing()

        # Calculate main thread time (time to queue all uploads)
        main_thread_time = time.time() - start_time
        logger.info(f"Main thread completed in {main_thread_time:.2f} seconds")

        # Wait for all uploads to complete
        logger.info("Main thread: Now waiting for background uploads to complete...")
        wait_start_time = time.time()
        wait_for_uploads()
        wait_time = time.time() - wait_start_time

        # Calculate total time
        total_time = time.time() - start_time

        logger.info(f"Asynchronous upload benchmark completed in {total_time:.2f} seconds")
        logger.info(f"Main thread time: {main_thread_time:.2f} seconds")
        logger.info(f"Wait time: {wait_time:.2f} seconds")

        return main_thread_time, total_time
    finally:
        # Stop the upload worker
        stop_upload_worker()


def run_benchmark(num_files=DEFAULT_NUM_FILES, file_size_kb=DEFAULT_FILE_SIZE_KB):
    """Run the benchmark comparison."""
    logger.info(f"Running upload benchmark with {num_files} files of {file_size_kb}KB each")

    # Check if AWS credentials are available
    if not (
        os.environ.get("AWS_SECRET_ACCESS_KEY")
        and os.environ.get("AWS_ACCESS_KEY_ID")
        and os.environ.get("AWS_S3_BUCKETNAME")
        and os.environ.get("AWS_S3_IMAGE_DIR")
    ):
        logger.error("AWS credentials not found in environment variables. Please set them in .env file.")
        return

    # Create a database connection
    db_manager = DatabaseManager()
    db = db_manager.connect()

    if db is None:
        logger.error("Failed to connect to the database. Check your database credentials.")
        return

    try:
        # Run synchronous benchmark
        sync_time = benchmark_sync_uploads(db, num_files, file_size_kb)

        # Add a separator
        logger.info("-" * 80)

        # Run asynchronous benchmark
        async_main_thread_time, async_total_time = benchmark_async_uploads(db, num_files, file_size_kb)

        # Calculate and display the results
        logger.info("\nBenchmark Results:")
        logger.info("-" * 80)
        logger.info(f"Number of files: {num_files}")
        logger.info(f"File size: {file_size_kb}KB each")
        logger.info(f"Simulated processing time between uploads: {PROCESSING_TIME:.2f} seconds")
        logger.info("-" * 80)
        logger.info(f"Synchronous upload total time: {sync_time:.2f} seconds")
        logger.info(f"Asynchronous upload main thread time: {async_main_thread_time:.2f} seconds")
        logger.info(f"Asynchronous upload total time: {async_total_time:.2f} seconds")
        logger.info("-" * 80)

        # Calculate speedup
        main_thread_speedup = sync_time / async_main_thread_time
        total_time_ratio = sync_time / async_total_time

        logger.info(f"Main thread speedup: {main_thread_speedup:.2f}x faster with async uploads")
        logger.info(f"Total time ratio: {total_time_ratio:.2f}x")
        logger.info(f"Time saved in main thread: {sync_time - async_main_thread_time:.2f} seconds")

        return {
            "sync_time": sync_time,
            "async_main_thread_time": async_main_thread_time,
            "async_total_time": async_total_time,
            "main_thread_speedup": main_thread_speedup,
            "total_time_ratio": total_time_ratio,
        }
    finally:
        # Close the database connection
        db.close()


def run_multiple_benchmarks():
    """Run multiple benchmarks with different parameters."""
    logger.info("Running multiple benchmarks with different parameters")

    # Define benchmark scenarios
    scenarios = [
        {"num_files": 5, "file_size_kb": 10, "description": "Small files, few uploads"},
        {"num_files": 10, "file_size_kb": 50, "description": "Medium files, medium uploads"},
        {"num_files": 20, "file_size_kb": 100, "description": "Large files, many uploads"},
    ]

    results = []

    for scenario in scenarios:
        logger.info("\n" + "=" * 80)
        logger.info(f"Benchmark Scenario: {scenario['description']}")
        logger.info("=" * 80)

        result = run_benchmark(scenario["num_files"], scenario["file_size_kb"])
        if result:
            results.append({"scenario": scenario, "results": result})

        # Add a separator between scenarios
        logger.info("\n\n")

    # Print summary of all benchmarks
    logger.info("\n" + "=" * 80)
    logger.info("Benchmark Summary")
    logger.info("=" * 80)

    for i, result_data in enumerate(results):
        scenario = result_data["scenario"]
        result = result_data["results"]

        logger.info(f"Scenario {i+1}: {scenario['description']}")
        logger.info(f"  - Files: {scenario['num_files']} x {scenario['file_size_kb']}KB")
        logger.info(f"  - Sync time: {result['sync_time']:.2f}s")
        logger.info(f"  - Async main thread time: {result['async_main_thread_time']:.2f}s")
        logger.info(f"  - Main thread speedup: {result['main_thread_speedup']:.2f}x")
        logger.info("")

    return results


if __name__ == "__main__":
    # Check if we should run multiple benchmarks
    if len(sys.argv) > 1 and sys.argv[1] == "--multiple":
        run_multiple_benchmarks()
    else:
        # Run a single benchmark with default parameters
        run_benchmark()
