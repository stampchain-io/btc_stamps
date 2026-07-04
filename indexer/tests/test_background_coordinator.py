"""
Test cases for the Background Coordinator system
"""

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from index_core.background_coordinator import BackgroundCoordinator


class TestBackgroundCoordinator(unittest.TestCase):
    """Test the background coordinator functionality"""

    def setUp(self):
        """Reset coordinator state before each test"""
        # Reset the singleton instance
        BackgroundCoordinator._instance = None
        self.coordinator = BackgroundCoordinator.get_instance()

    def tearDown(self):
        """Clean up after each test"""
        # Reset the singleton instance
        BackgroundCoordinator._instance = None

    def test_singleton_pattern(self):
        """Test that coordinator follows singleton pattern"""
        coord1 = BackgroundCoordinator.get_instance()
        coord2 = BackgroundCoordinator.get_instance()
        self.assertIs(coord1, coord2)

    def test_start_and_end_task(self):
        """Test basic task start and end"""
        # Should be able to start a task
        self.assertTrue(self.coordinator.start_task("test_task"))
        self.assertIn("test_task", self.coordinator.active_tasks)

        # Should not be able to start the same task again
        self.assertFalse(self.coordinator.start_task("test_task"))

        # Should be able to end the task
        self.coordinator.end_task("test_task")
        self.assertNotIn("test_task", self.coordinator.active_tasks)

    def test_heavy_task_exclusion(self):
        """Test that heavy tasks exclude each other"""
        # Start a heavy task
        self.assertTrue(self.coordinator.start_task("heavy_task_1", is_heavy=True))
        self.assertTrue(self.coordinator.heavy_operation_in_progress)

        # Should not be able to start another heavy task
        self.assertFalse(self.coordinator.start_task("heavy_task_2", is_heavy=True))

        # Should be able to start a light task
        self.assertTrue(self.coordinator.start_task("light_task"))

        # End the heavy task
        self.coordinator.end_task("heavy_task_1", is_heavy=True)
        self.assertFalse(self.coordinator.heavy_operation_in_progress)

        # Now should be able to start another heavy task
        self.assertTrue(self.coordinator.start_task("heavy_task_2", is_heavy=True))

    def test_can_start_task(self):
        """Test the can_start_task method"""
        # Should be able to check if a task can start
        self.assertTrue(self.coordinator.can_start_task("test_task"))

        # Start a heavy task
        self.coordinator.start_task("heavy_task", is_heavy=True)

        # Light task should still be checkable
        self.assertTrue(self.coordinator.can_start_task("light_task"))

        # Heavy task should not be startable
        self.assertFalse(self.coordinator.can_start_task("another_heavy_task", is_heavy=True))

    def test_task_already_running(self):
        """Test that same task cannot run twice"""
        # Start a task
        self.assertTrue(self.coordinator.start_task("duplicate_task"))

        # Try to start the same task again
        self.assertFalse(self.coordinator.start_task("duplicate_task"))

        # End the task
        self.coordinator.end_task("duplicate_task")

        # Now should be able to start it again
        self.assertTrue(self.coordinator.start_task("duplicate_task"))

    def test_concurrent_access(self):
        """Test thread safety of coordinator"""
        results = []
        barrier = threading.Barrier(3)

        def try_start_heavy_task(task_name):
            barrier.wait()  # Synchronize all threads
            result = self.coordinator.start_task(task_name, is_heavy=True)
            results.append((task_name, result))
            if result:
                time.sleep(0.1)  # Simulate work
                self.coordinator.end_task(task_name, is_heavy=True)

        # Create three threads trying to start heavy tasks
        threads = []
        for i in range(3):
            t = threading.Thread(target=try_start_heavy_task, args=(f"heavy_task_{i}",))
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # Only one heavy task should have succeeded
        successful_tasks = [r for r in results if r[1]]
        self.assertEqual(len(successful_tasks), 1)

    def test_error_handling(self):
        """Test coordinator behavior with errors"""
        # Start a task
        self.assertTrue(self.coordinator.start_task("error_task"))

        # Simulate an error occurring during task execution
        # Task should still be removable
        self.coordinator.end_task("error_task")
        self.assertNotIn("error_task", self.coordinator.active_tasks)

        # Should be able to start the task again
        self.assertTrue(self.coordinator.start_task("error_task"))

    def test_multiple_light_tasks(self):
        """Test that multiple light tasks can run concurrently"""
        # Start multiple light tasks
        for i in range(5):
            self.assertTrue(self.coordinator.start_task(f"light_task_{i}"))

        # All should be in active tasks
        self.assertEqual(len(self.coordinator.active_tasks), 5)

        # End all tasks
        for i in range(5):
            self.coordinator.end_task(f"light_task_{i}")

        # Active tasks should be empty
        self.assertEqual(len(self.coordinator.active_tasks), 0)

    def test_real_world_scenario(self):
        """Test a real-world scenario with market data, sales history, and holder updates"""
        # Start market data update (heavy)
        self.assertTrue(self.coordinator.start_task("market_data_stamps", is_heavy=True))

        # Sales history should be blocked
        self.assertFalse(self.coordinator.start_task("sales_history", is_heavy=True))

        # Holder update should be blocked
        self.assertFalse(self.coordinator.start_task("holder_update", is_heavy=True))

        # End market data update
        self.coordinator.end_task("market_data_stamps", is_heavy=True)

        # Now sales history should be able to start
        self.assertTrue(self.coordinator.start_task("sales_history", is_heavy=True))

        # But holder update should still be blocked
        self.assertFalse(self.coordinator.start_task("holder_update", is_heavy=True))

        # End sales history
        self.coordinator.end_task("sales_history", is_heavy=True)

        # Now holder update should be able to start
        self.assertTrue(self.coordinator.start_task("holder_update", is_heavy=True))

    def test_stats_tracking(self):
        """Test that coordinator tracks task statistics"""
        initial_stats = self.coordinator.get_stats()
        self.assertEqual(initial_stats["active_task_count"], 0)
        self.assertFalse(initial_stats["heavy_operation_in_progress"])

        # Start some tasks
        self.coordinator.start_task("task1")
        self.coordinator.start_task("task2", is_heavy=True)

        stats = self.coordinator.get_stats()
        self.assertEqual(stats["active_task_count"], 2)
        self.assertTrue(stats["heavy_operation_in_progress"])
        self.assertIn("task1", stats["active_tasks"])
        self.assertIn("task2", stats["active_tasks"])

        # End tasks
        self.coordinator.end_task("task1")
        self.coordinator.end_task("task2", is_heavy=True)

        final_stats = self.coordinator.get_stats()
        self.assertEqual(final_stats["active_task_count"], 0)
        self.assertFalse(final_stats["heavy_operation_in_progress"])


class TestCoordinatorIntegration(unittest.TestCase):
    """Test coordinator integration with actual components"""

    @patch("index_core.background_coordinator.logger")
    def test_logging_behavior(self, mock_logger):
        """Test that coordinator logs appropriately"""
        coordinator = BackgroundCoordinator.get_instance()

        # Start a heavy task
        coordinator.start_task("test_heavy", is_heavy=True)
        mock_logger.debug.assert_called()

        # Try to start another heavy task
        coordinator.start_task("test_heavy_2", is_heavy=True)
        # Should log that it cannot start
        self.assertTrue(any("Cannot start" in str(call) for call in mock_logger.debug.call_args_list))

        # Clean up
        coordinator.end_task("test_heavy", is_heavy=True)
        BackgroundCoordinator._instance = None


if __name__ == "__main__":
    unittest.main()
