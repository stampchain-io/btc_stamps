"""Tests for profiling module."""

import os
import tempfile
import unittest
from unittest import mock

from index_core.profiling import Profiler, get_function_stats, profile_function


class TestProfiling(unittest.TestCase):
    """Test profiling functionality."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @mock.patch("index_core.profiling.config.DEBUG_PROFILING", False)
    def test_profiler_disabled(self):
        """Test Profiler when profiling is disabled."""
        profiler = Profiler()

        # Should not set up profiling when disabled
        self.assertFalse(profiler.profiling_enabled)
        self.assertIsNone(profiler.profile_dir)
        self.assertIsNone(profiler.profiler)

        # Methods should return early when disabled
        profiler.start_block_profiling()
        profiler.end_block_profiling()

        # No profiling should have occurred
        self.assertEqual(profiler.blocks_profiled, 0)
        self.assertFalse(profiler.profiling_active)

    @mock.patch("index_core.profiling.config.DEBUG_PROFILING", True)
    def test_profiler_enabled_setup(self):
        """Test Profiler setup when profiling is enabled."""
        with mock.patch("os.makedirs") as mock_makedirs:
            with mock.patch("builtins.open", mock.mock_open()):
                with mock.patch("os.remove"):
                    profiler = Profiler()

                # Should set up profiling when enabled
                self.assertTrue(profiler.profiling_enabled)
                self.assertIsNotNone(profiler.profile_dir)
                self.assertIsNotNone(profiler.profiler)
                self.assertIsNotNone(profiler.timestamp)

                # Verify directory creation was attempted
                mock_makedirs.assert_called_once()

    @mock.patch("index_core.profiling.config.DEBUG_PROFILING", True)
    @mock.patch("index_core.profiling.util.CURRENT_BLOCK_INDEX", 1000)
    def test_start_block_profiling(self):
        """Test starting block profiling."""
        with mock.patch("os.makedirs"):
            with mock.patch("builtins.open", mock.mock_open()):
                with mock.patch("os.remove"):
                    profiler = Profiler()

                    # First block should be skipped
                    profiler.start_block_profiling()
                    self.assertTrue(profiler.first_block_skipped)
                    self.assertFalse(profiler.profiling_active)
                    self.assertEqual(profiler.blocks_seen, 1)

                    # Second block should start profiling
                    profiler.start_block_profiling()
                    self.assertTrue(profiler.profiling_active)
                    self.assertEqual(profiler.blocks_seen, 2)
                    self.assertEqual(profiler.start_block, 1000)
                    self.assertIsNotNone(profiler.stats_file)
                    self.assertIsNotNone(profiler.profile_data_file)

    @mock.patch("index_core.profiling.config.DEBUG_PROFILING", True)
    @mock.patch("index_core.profiling.util.CURRENT_BLOCK_INDEX", 1000)
    def test_end_block_profiling(self):
        """Test ending block profiling."""
        with mock.patch("os.makedirs"):
            with mock.patch("builtins.open", mock.mock_open()):
                with mock.patch("os.remove"):
                    profiler = Profiler()

                    # Skip first block
                    profiler.start_block_profiling()

                    # Start profiling on second block
                    profiler.start_block_profiling()

                    # End profiling for the block
                    profiler.end_block_profiling()
                    self.assertEqual(profiler.blocks_profiled, 1)

                    # Profiler should still be active (not yet at 20 blocks)
                    self.assertTrue(profiler.profiling_active)

    @mock.patch("index_core.profiling.config.DEBUG_PROFILING", True)
    def test_profiler_20_blocks_limit(self):
        """Test that profiler stops after 20 blocks."""
        with mock.patch("os.makedirs"):
            with mock.patch("builtins.open", mock.mock_open()):
                with mock.patch("os.remove"):
                    profiler = Profiler()
                    profiler.blocks_profiled = 20

                    # Should not start new profiling when already at 20 blocks
                    profiler.start_block_profiling()
                    self.assertEqual(profiler.blocks_profiled, 20)

    @mock.patch("index_core.profiling.config.DEBUG_PROFILING", False)
    def test_profile_function_decorator_disabled(self):
        """Test profile_function decorator when profiling is disabled."""

        @profile_function
        def test_func(x, y):
            return x + y

        # Function should work normally
        result = test_func(1, 2)
        self.assertEqual(result, 3)

        # No profiler should be created
        self.assertFalse(hasattr(profile_function, "profiler"))

    @mock.patch("index_core.profiling.config.DEBUG_PROFILING", True)
    def test_profile_function_decorator_enabled(self):
        """Test profile_function decorator when profiling is enabled."""

        @profile_function
        def test_func(x, y):
            return x + y

        # Function should work normally
        result = test_func(1, 2)
        self.assertEqual(result, 3)

        # Profiler should be created
        self.assertTrue(hasattr(profile_function, "profiler"))

        # Should be able to get stats
        stats = get_function_stats()
        self.assertIsNotNone(stats)

    @mock.patch("index_core.profiling.config.DEBUG_PROFILING", True)
    def test_profile_function_with_exception(self):
        """Test profile_function decorator handles exceptions properly."""

        @profile_function
        def test_func():
            raise ValueError("Test error")

        # Exception should be propagated
        with self.assertRaises(ValueError) as context:
            test_func()
        self.assertEqual(str(context.exception), "Test error")

    def test_get_function_stats_no_profiler(self):
        """Test get_function_stats when no profiler exists."""
        # Clear any existing profiler
        if hasattr(profile_function, "profiler"):
            delattr(profile_function, "profiler")

        stats = get_function_stats()
        self.assertIsNone(stats)

    @mock.patch("index_core.profiling.config.DEBUG_PROFILING", True)
    def test_save_profile_data(self):
        """Test _save_profile_data method."""
        with mock.patch("os.makedirs"):
            with mock.patch("builtins.open", mock.mock_open()):
                with mock.patch("os.remove"):
                    profiler = Profiler()

                    # Skip first block and start profiling
                    profiler.start_block_profiling()
                    profiler.start_block_profiling()

                    # Mock profiler dump_stats and pstats
                    with mock.patch.object(profiler.profiler, "dump_stats") as mock_dump:
                        with mock.patch("index_core.profiling.pstats.Stats") as mock_stats:
                            mock_stats_instance = mock.Mock()
                            mock_stats.return_value = mock_stats_instance

                            # Call _save_profile_data directly
                            profiler._save_profile_data()

                            # Should save data and disable profiler
                            mock_dump.assert_called_once()
                            self.assertFalse(profiler.profiling_active)


if __name__ == "__main__":
    unittest.main()
