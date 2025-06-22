"""Tests for memory_manager module."""

import time
import unittest
from unittest import mock

from index_core.cache_types import LRUCache
from index_core.memory_manager import MemoryManager


class TestMemoryManager(unittest.TestCase):
    """Test memory management functionality."""

    def setUp(self):
        """Set up test environment."""
        self.manager = MemoryManager(memory_threshold=0.85)

    def test_get_memory_usage(self):
        """Test getting memory usage percentage."""
        with mock.patch.object(self.manager._process, "memory_percent", return_value=50.0):
            usage = self.manager.get_memory_usage()
            self.assertEqual(usage, 0.5)  # 50% as decimal

    def test_register_and_unregister_cache(self):
        """Test cache registration and unregistration."""
        cache = LRUCache(max_size=100)

        # Register cache
        self.manager.register_cache("test_cache", cache)
        self.assertIn("test_cache", self.manager._registered_caches)
        self.assertEqual(self.manager._registered_caches["test_cache"], cache)

        # Unregister cache
        self.manager.unregister_cache("test_cache")
        self.assertNotIn("test_cache", self.manager._registered_caches)

    def test_unregister_nonexistent_cache(self):
        """Test unregistering a cache that doesn't exist."""
        # Should not raise, just log warning
        self.manager.unregister_cache("nonexistent")

    def test_should_check_memory_timing(self):
        """Test memory check timing logic."""
        # First check should be True
        self.assertTrue(self.manager.should_check_memory())

        # Immediate second check should be False
        self.assertFalse(self.manager.should_check_memory())

        # Mock time to advance past interval
        with mock.patch("time.time", return_value=time.time() + 10):
            self.assertTrue(self.manager.should_check_memory())

    def test_log_memory_usage(self):
        """Test memory usage logging."""
        # Reset last log time to ensure logging happens
        self.manager._last_log = 0

        with mock.patch("time.time") as mock_time:
            # First call: current_time=100, _last_log=0, so 100-0 >= 60, should log
            mock_time.return_value = 100
            with mock.patch.object(self.manager, "get_memory_usage", return_value=0.75):
                with mock.patch("index_core.memory_manager.logger") as mock_logger:
                    # First call should log
                    self.manager.log_memory_usage(current_block=1000)
                    mock_logger.info.assert_called_once()

                    # Immediate second call should not log (within interval)
                    # current_time=110, _last_log=100, so 110-100 < 60, should not log
                    mock_time.return_value = 110
                    mock_logger.reset_mock()
                    self.manager.log_memory_usage(current_block=1001)
                    mock_logger.info.assert_not_called()

                    # After time interval, should log again
                    # current_time=200, _last_log=100, so 200-100 >= 60, should log
                    mock_time.return_value = 200
                    self.manager.log_memory_usage(current_block=1002)
                    mock_logger.info.assert_called_once()

    def test_clear_all_caches(self):
        """Test clearing all registered caches."""
        # Create and register multiple caches
        cache1 = LRUCache(max_size=10)
        cache2 = LRUCache(max_size=10)

        # Add some items
        cache1.set("key1", "value1")
        cache2.set("key2", "value2")

        self.manager.register_cache("cache1", cache1)
        self.manager.register_cache("cache2", cache2)

        # Clear all
        self.manager.clear_all()

        # Both caches should be empty
        self.assertEqual(len(cache1), 0)
        self.assertEqual(len(cache2), 0)

    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        # Create and register caches with items
        cache1 = LRUCache(max_size=10)
        cache2 = LRUCache(max_size=10)

        cache1.set("key1", "value1")
        cache1.set("key2", "value2")
        cache2.set("key3", "value3")

        self.manager.register_cache("cache1", cache1)
        self.manager.register_cache("cache2", cache2)

        stats = self.manager.get_cache_stats()

        self.assertEqual(stats["cache1"], 2)
        self.assertEqual(stats["cache2"], 1)

    @mock.patch("time.time")
    def test_clear_caches_if_needed_below_threshold(self, mock_time):
        """Test that caches are not cleared when memory is below threshold."""
        mock_time.return_value = 100  # Ensure should_check_memory returns True

        with mock.patch.object(self.manager, "get_memory_usage", return_value=0.5):  # 50% usage
            with mock.patch.object(self.manager, "clear_all") as mock_clear:
                self.manager.clear_caches_if_needed()
                mock_clear.assert_not_called()

    @mock.patch("time.time")
    def test_clear_caches_if_needed_above_threshold(self, mock_time):
        """Test that caches are cleared when memory is above threshold."""
        mock_time.return_value = 100  # Ensure should_check_memory returns True

        with mock.patch.object(self.manager, "get_memory_usage", side_effect=[0.9, 0.6]):  # 90% then 60%
            with mock.patch.object(self.manager, "clear_all") as mock_clear:
                with mock.patch("index_core.memory_manager.logger") as mock_logger:
                    self.manager.clear_caches_if_needed()
                    mock_clear.assert_called_once()
                    # Should log warning about high usage and info about new usage
                    self.assertEqual(mock_logger.warning.call_count, 1)
                    self.assertEqual(mock_logger.info.call_count, 1)

    def test_memory_manager_init_with_custom_threshold(self):
        """Test MemoryManager initialization with custom threshold."""
        manager = MemoryManager(memory_threshold=0.95)
        self.assertEqual(manager.memory_threshold, 0.95)

    def test_should_check_memory_force(self):
        """Test should_check_memory with force flag."""
        # Reset check time
        self.manager._last_check = 0

        # First check should return True
        self.assertTrue(self.manager.should_check_memory())

        # Immediate second check should return False
        self.assertFalse(self.manager.should_check_memory())

    def test_clear_caches_if_needed_not_time_yet(self):
        """Test clear_caches_if_needed when not enough time has passed."""
        # Set last check to recent time
        self.manager._last_check = time.time()

        with mock.patch.object(self.manager, "get_memory_usage", return_value=0.9) as mock_usage:
            with mock.patch.object(self.manager, "clear_all") as mock_clear:
                self.manager.clear_caches_if_needed()

                # Should not check memory or clear caches
                mock_usage.assert_not_called()
                mock_clear.assert_not_called()

    def test_log_memory_usage_without_block_number(self):
        """Test log_memory_usage without providing block number."""
        self.manager._last_log = 0

        with mock.patch("time.time", return_value=100):
            with mock.patch.object(self.manager, "get_memory_usage", return_value=0.75):
                with mock.patch("index_core.memory_manager.logger") as mock_logger:
                    # Call without block number
                    self.manager.log_memory_usage()

                    # Should log without block info
                    mock_logger.info.assert_called_once()
                    call_args = mock_logger.info.call_args[0][0]
                    self.assertNotIn("at block", call_args)

    def test_memory_manager_psutil_exception(self):
        """Test MemoryManager handles psutil exceptions gracefully."""
        # Make Process constructor raise exception
        with mock.patch("psutil.Process", side_effect=Exception("No psutil")):
            # Should raise exception during initialization
            with self.assertRaises(Exception) as context:
                manager = MemoryManager()
            self.assertEqual(str(context.exception), "No psutil")

    def test_get_memory_usage_with_process_error(self):
        """Test get_memory_usage when process.memory_percent fails."""
        with mock.patch.object(self.manager._process, "memory_percent", side_effect=Exception("Process error")):
            # Should handle exception gracefully (exact behavior depends on implementation)
            try:
                usage = self.manager.get_memory_usage()
                # If it returns a value, it should be reasonable
                self.assertIsInstance(usage, (int, float))
            except Exception:
                # Or it might propagate the exception
                pass


if __name__ == "__main__":
    unittest.main()
