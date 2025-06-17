#!/usr/bin/env python
"""
ThreadPoolExecutor lifecycle management test for CPBlocksPipeline

This test validates that the fix for the "cannot schedule new futures after shutdown"
error works correctly during pipeline reset operations.
"""

import logging

# Add src directory to path
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

current_dir = Path(__file__).parent.parent.absolute()
src_path = current_dir / "src"
sys.path.insert(0, str(src_path))

from index_core.pipeline_utils import CPBlocksPipeline

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TestPipelineExecutorLifecycle(unittest.TestCase):
    """Test ThreadPoolExecutor lifecycle management in CPBlocksPipeline"""

    def setUp(self):
        """Set up test fixtures"""
        self.pipeline = None
        self.test_results = []
        self.error_results = []

    def tearDown(self):
        """Clean up test fixtures"""
        if self.pipeline:
            try:
                self.pipeline.stop()
            except Exception as e:
                logger.warning(f"Error stopping pipeline in tearDown: {e}")

    def _mock_all_network_calls(self):
        """Context manager to mock all network and external calls"""
        # Mock all external dependencies to prevent real network calls
        mocks = [
            patch("index_core.pipeline_utils.backend_instance"),
            patch("index_core.pipeline_utils.config.CP_STAMP_GENESIS_BLOCK", 100000),
            patch("index_core.pipeline_utils.update_healthy_nodes"),
            patch("index_core.pipeline_utils.fetch_xcp_blocks_concurrent", return_value={}),
            patch("index_core.pipeline_utils.is_shutdown_requested", return_value=False),
            patch("index_core.node_health.get_healthy_nodes", return_value=[]),
            patch("index_core.node_health.update_healthy_nodes"),
        ]

        return mocks

    def test_executor_lifecycle_during_reset(self):
        """
        Test that pipeline can submit tasks after reset() operation.
        This validates the fix for the ThreadPoolExecutor lifecycle issue.
        """
        logger.info("Testing ThreadPoolExecutor lifecycle during reset operation")

        # Mock all external dependencies
        with patch("index_core.pipeline_utils.backend_instance") as mock_backend, patch(
            "index_core.pipeline_utils.config.CP_STAMP_GENESIS_BLOCK", 100000
        ), patch("index_core.pipeline_utils.update_healthy_nodes"), patch(
            "index_core.pipeline_utils.get_healthy_nodes", return_value=[{"name": "test_node", "url": "http://test:4000/v2"}]
        ), patch(
            "index_core.pipeline_utils.fetch_xcp_blocks_concurrent", return_value={}
        ), patch(
            "index_core.pipeline_utils.is_shutdown_requested", return_value=False
        ), patch.object(
            CPBlocksPipeline, "wait_for_initial_blocks", return_value=True
        ):

            mock_backend.getblockcount.return_value = 100010
            mock_backend.invalidate_blockcount_cache.return_value = None

            self.pipeline = CPBlocksPipeline(max_queue_size=10, fallback_mode=False)

            # Start the pipeline (this should not make real network calls)
            self.pipeline.start(start_block=100000)

            # Wait a moment for initialization
            time.sleep(0.1)

            # Verify initial executor exists and is not shutdown
            self.assertIsNotNone(self.pipeline.fetch_executor)
            self.assertFalse(self.pipeline.fetch_executor._shutdown)

            # Submit a test task to verify executor works
            future1 = self._submit_test_task("initial_task")
            self.assertTrue(future1.done() or not future1.cancelled())

            # Store the original executor reference
            original_executor = self.pipeline.fetch_executor

            # Call reset() - this is where the bug occurred
            logger.info("Calling pipeline.reset() - this should create new executor")
            self.pipeline.reset(new_start_block=100010)

            # Verify the old executor was shutdown
            self.assertTrue(original_executor._shutdown, "Original executor should be shutdown after reset")

            # Verify a new executor was created
            self.assertIsNotNone(self.pipeline.fetch_executor)
            self.assertNotEqual(
                original_executor, self.pipeline.fetch_executor, "Pipeline should have new executor after reset"
            )

            # Critical test: Verify new executor is not shutdown
            self.assertFalse(self.pipeline.fetch_executor._shutdown, "New executor should not be shutdown")

            # Critical test: Try to submit tasks to new executor
            # This would fail with "cannot schedule new futures after shutdown" before fix
            logger.info("Testing task submission after reset (this would fail before fix)")

            future2 = self._submit_test_task("post_reset_task")

            # Verify the task was submitted successfully
            self.assertIsNotNone(future2, "Should be able to submit task after reset")
            self.assertFalse(future2.cancelled(), "Task should not be cancelled")

            # Test multiple consecutive task submissions
            futures = []
            for i in range(5):
                future = self._submit_test_task(f"batch_task_{i}")
                futures.append(future)

            # Verify all tasks were submitted successfully
            for i, future in enumerate(futures):
                self.assertIsNotNone(future, f"Batch task {i} should submit successfully")
                self.assertFalse(future.cancelled(), f"Batch task {i} should not be cancelled")

    def test_multiple_resets(self):
        """Test that multiple reset operations work correctly"""
        logger.info("Testing multiple consecutive reset operations")

        with patch("index_core.pipeline_utils.backend_instance") as mock_backend, patch(
            "index_core.pipeline_utils.config.CP_STAMP_GENESIS_BLOCK", 100000
        ), patch("index_core.pipeline_utils.update_healthy_nodes"), patch(
            "index_core.pipeline_utils.get_healthy_nodes", return_value=[{"name": "test_node", "url": "http://test:4000/v2"}]
        ), patch(
            "index_core.pipeline_utils.fetch_xcp_blocks_concurrent", return_value={}
        ), patch(
            "index_core.pipeline_utils.is_shutdown_requested", return_value=False
        ), patch.object(
            CPBlocksPipeline, "wait_for_initial_blocks", return_value=True
        ):

            mock_backend.getblockcount.return_value = 100010
            mock_backend.invalidate_blockcount_cache.return_value = None

            self.pipeline = CPBlocksPipeline(max_queue_size=10, fallback_mode=False)
            self.pipeline.start(start_block=100000)

            time.sleep(0.1)

            # Perform multiple resets
            for i in range(3):
                logger.info(f"Reset iteration {i + 1}")

                # Submit task before reset
                future_before = self._submit_test_task(f"before_reset_{i}")
                self.assertIsNotNone(future_before)

                # Store executor reference
                executor_before = self.pipeline.fetch_executor

                # Reset pipeline
                self.pipeline.reset(new_start_block=100000 + i * 10)

                # Verify new executor
                executor_after = self.pipeline.fetch_executor
                self.assertNotEqual(executor_before, executor_after, f"Reset {i + 1} should create new executor")
                self.assertTrue(executor_before._shutdown, f"Old executor {i + 1} should be shutdown")
                self.assertFalse(executor_after._shutdown, f"New executor {i + 1} should not be shutdown")

                # Submit task after reset
                future_after = self._submit_test_task(f"after_reset_{i}")
                self.assertIsNotNone(future_after)
                self.assertFalse(future_after.cancelled())

    def test_concurrent_reset_and_task_submission(self):
        """Test reset operation while tasks are being submitted"""
        logger.info("Testing concurrent reset and task submission")

        with patch("index_core.pipeline_utils.backend_instance") as mock_backend, patch(
            "index_core.pipeline_utils.config.CP_STAMP_GENESIS_BLOCK", 100000
        ), patch("index_core.pipeline_utils.update_healthy_nodes"), patch(
            "index_core.pipeline_utils.get_healthy_nodes", return_value=[{"name": "test_node", "url": "http://test:4000/v2"}]
        ), patch(
            "index_core.pipeline_utils.fetch_xcp_blocks_concurrent", return_value={}
        ), patch(
            "index_core.pipeline_utils.is_shutdown_requested", return_value=False
        ), patch.object(
            CPBlocksPipeline, "wait_for_initial_blocks", return_value=True
        ):

            mock_backend.getblockcount.return_value = 100010
            mock_backend.invalidate_blockcount_cache.return_value = None

            self.pipeline = CPBlocksPipeline(max_queue_size=10, fallback_mode=False)
            self.pipeline.start(start_block=100000)

            time.sleep(0.1)

            # Start background task submission
            stop_submission = threading.Event()
            submission_thread = threading.Thread(target=self._continuous_task_submission, args=(stop_submission,))
            submission_thread.start()

            try:
                # Wait a moment for submissions to start
                time.sleep(0.2)

                # Perform reset while tasks are being submitted
                self.pipeline.reset(new_start_block=100020)

                # Continue submissions for a bit more
                time.sleep(0.2)

                # Stop background submissions
                stop_submission.set()
                submission_thread.join(timeout=2.0)

                # Verify pipeline is still functional
                final_future = self._submit_test_task("final_verification")
                self.assertIsNotNone(final_future)
                self.assertFalse(final_future.cancelled())

                # Verify we didn't get any "shutdown" errors
                self.assertEqual(len(self.error_results), 0, f"Should not have executor shutdown errors: {self.error_results}")

            finally:
                stop_submission.set()
                if submission_thread.is_alive():
                    submission_thread.join(timeout=1.0)

    def test_pipeline_functionality_after_reset(self):
        """Test that pipeline retains full functionality after reset"""
        logger.info("Testing complete pipeline functionality after reset")

        with patch("index_core.pipeline_utils.backend_instance") as mock_backend, patch(
            "index_core.pipeline_utils.config.CP_STAMP_GENESIS_BLOCK", 100000
        ), patch("index_core.pipeline_utils.update_healthy_nodes"), patch(
            "index_core.pipeline_utils.get_healthy_nodes", return_value=[{"name": "test_node", "url": "http://test:4000/v2"}]
        ), patch(
            "index_core.pipeline_utils.fetch_xcp_blocks_concurrent", return_value={}
        ), patch(
            "index_core.pipeline_utils.is_shutdown_requested", return_value=False
        ), patch.object(
            CPBlocksPipeline, "wait_for_initial_blocks", return_value=True
        ):

            mock_backend.getblockcount.return_value = 100010
            mock_backend.invalidate_blockcount_cache.return_value = None

            self.pipeline = CPBlocksPipeline(max_queue_size=10, fallback_mode=False)
            self.pipeline.start(start_block=100000)

            time.sleep(0.1)

            # Test pipeline methods before reset (pipeline advances current_block based on tip)
            self.assertIn(self.pipeline.current_block, [100000, 100010])

            # Reset pipeline
            self.pipeline.reset(new_start_block=100050)

            # Verify pipeline state after reset
            self.assertEqual(self.pipeline.current_block, 100050)
            self.assertEqual(len(self.pipeline.queue), 0, "Queue should be cleared after reset")

            # Test that pipeline can still process blocks
            # This should work without throwing the "cannot schedule new futures after shutdown" error
            _ = self.pipeline.get_block(100050)
            # We expect None since we're mocking the fetch to return empty results
            # The important thing is that no executor errors occur

    def _submit_test_task(self, task_name):
        """Submit a simple test task to the pipeline executor"""
        try:

            def test_task():
                logger.debug(f"Executing test task: {task_name}")
                time.sleep(0.01)  # Small delay to simulate work
                return f"completed_{task_name}"

            future = self.pipeline.fetch_executor.submit(test_task)
            self.test_results.append(task_name)
            return future

        except RuntimeError as e:
            # This is the error we're testing for
            if "cannot schedule new futures after shutdown" in str(e):
                self.error_results.append(f"{task_name}: {str(e)}")
                logger.error(f"CRITICAL: Got executor shutdown error for {task_name}: {e}")
                raise AssertionError(f"ThreadPoolExecutor lifecycle fix failed: {e}")
            else:
                raise

    def _continuous_task_submission(self, stop_event):
        """Continuously submit tasks until stop event is set"""
        task_count = 0
        while not stop_event.is_set():
            try:
                task_count += 1
                future = self._submit_test_task(f"continuous_{task_count}")
                if future:
                    time.sleep(0.05)  # Small delay between submissions
            except Exception as e:
                self.error_results.append(f"continuous_{task_count}: {str(e)}")
                logger.error(f"Error in continuous submission: {e}")
                break


if __name__ == "__main__":
    # Run the tests
    unittest.main(verbosity=2)
