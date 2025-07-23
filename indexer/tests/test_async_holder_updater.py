#!/usr/bin/env python3
"""
Test async holder count updater functionality.
"""

import time
from unittest.mock import Mock, patch

import pytest

from index_core.async_holder_updater import (
    HolderUpdateTask,
    get_queue_size,
    is_worker_running,
    schedule_holder_update,
    start_worker,
    stop_worker,
    update_queue,
)


class TestAsyncHolderUpdater:
    """Test the async holder updater functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Reset the coordinator singleton to ensure clean state
        from index_core.background_coordinator import BackgroundCoordinator

        BackgroundCoordinator._instance = None

        # Ensure worker is stopped before each test
        if is_worker_running():
            stop_worker(timeout=1.0)

        # Recreate the executor if it was shut down
        from concurrent.futures import ThreadPoolExecutor

        import index_core.async_holder_updater

        if index_core.async_holder_updater.update_executor._shutdown:
            index_core.async_holder_updater.update_executor = ThreadPoolExecutor(max_workers=1)

        # Clear the queue
        while not update_queue.empty():
            try:
                update_queue.get_nowait()
            except:
                break

    def teardown_method(self):
        """Clean up after tests."""
        # Ensure worker is stopped
        if is_worker_running():
            stop_worker(timeout=1.0)

        # Reset the coordinator singleton
        from index_core.background_coordinator import BackgroundCoordinator

        BackgroundCoordinator._instance = None

    def test_start_stop_worker(self):
        """Test starting and stopping the worker."""
        assert not is_worker_running()

        start_worker()
        assert is_worker_running()

        stop_worker(timeout=1.0)
        assert not is_worker_running()

    def test_schedule_update(self):
        """Test scheduling holder updates."""
        start_worker()

        # Schedule an update
        affected_tokens = {"TEST", "KEVIN", "STAMP"}
        result = schedule_holder_update(906394, affected_tokens)

        assert result is True
        assert get_queue_size() == 1

        # Wait for processing
        time.sleep(0.5)

        stop_worker(timeout=1.0)

    def test_schedule_without_worker(self):
        """Test scheduling when worker is not running."""
        assert not is_worker_running()

        affected_tokens = {"TEST"}
        result = schedule_holder_update(906394, affected_tokens)

        assert result is False

    def test_empty_tokens_not_scheduled(self):
        """Test that empty token sets are not scheduled."""
        start_worker()

        result = schedule_holder_update(906394, set())
        assert result is True  # Returns True but doesn't queue
        assert get_queue_size() == 0

        stop_worker(timeout=1.0)

    @patch("index_core.async_holder_updater.SRC20HolderCountUpdater")
    def test_task_processing(self, mock_updater_class):
        """Test that tasks are processed correctly."""
        # Import and patch coordinator where it's actually used
        with patch("index_core.async_holder_updater._process_update_task") as mock_process:
            # Create a simpler mock that just tracks calls
            calls = []

            def track_call(task):
                calls.append(task)

            mock_process.side_effect = track_call

            start_worker()

            # Schedule an update
            affected_tokens = {"TEST", "KEVIN"}
            schedule_holder_update(906394, affected_tokens)

            # Wait for processing
            time.sleep(1.0)

            # Verify the task was processed
            assert len(calls) == 1
            task = calls[0]
            assert isinstance(task, HolderUpdateTask)
            assert task.block_index == 906394
            assert task.affected_tokens == affected_tokens
            assert task.force is False

            stop_worker(timeout=1.0)

    def test_force_update(self):
        """Test force update scheduling."""
        start_worker()

        # Schedule a force update
        result = schedule_holder_update(906394, set(), force=True)

        assert result is True
        assert get_queue_size() == 1

        # Get the task from queue to verify
        task = update_queue.get_nowait()
        assert isinstance(task, HolderUpdateTask)
        assert task.force is True
        assert task.block_index == 906394

        stop_worker(timeout=1.0)

    def test_queue_overflow_warning(self, caplog):
        """Test warning when queue gets large."""
        # Mock the process function to do nothing (fast processing)
        with patch("index_core.async_holder_updater._process_update_task"):
            start_worker()

            # Fill the queue to trigger warning (>10 items)
            for i in range(11):
                schedule_holder_update(906394 + i, {"TEST"})

            # Give time for warning
            time.sleep(0.5)

            # Check for warning
            warning_found = any("queue size is" in record.message for record in caplog.records)

            # Clear the queue manually to speed up shutdown
            while not update_queue.empty():
                try:
                    update_queue.get_nowait()
                    update_queue.task_done()
                except:
                    break

            stop_worker(timeout=1.0)

            assert warning_found


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
