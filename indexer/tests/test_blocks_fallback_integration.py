"""
Integration tests for fallback mode functionality within blocks.py

These tests focus on testing the integration points between blocks.py
and the CPBlocksPipeline fallback mode using established mocking patterns.
"""

import os
import sys
import unittest.mock as mock
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config
from index_core.pipeline_utils import CPBlocksPipeline


class TestBlocksFallbackIntegration:
    """Test fallback mode integration in blocks.py"""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup method run before each test."""
        self.original_fallback_mode = config.CP_FALLBACK_MODE

        # Clean up any existing state manager to prevent test interference
        import index_core.fallback_state

        index_core.fallback_state._state_manager = None

    def teardown_method(self):
        """Cleanup method run after each test."""
        config.CP_FALLBACK_MODE = self.original_fallback_mode

        # Clean up state manager after test
        import index_core.fallback_state

        if index_core.fallback_state._state_manager:
            try:
                index_core.fallback_state._state_manager.cleanup_state_file()
            except:
                pass
            index_core.fallback_state._state_manager = None

    def test_pipeline_initialization_with_fallback_enabled(self):
        """Test pipeline initialization with fallback mode enabled"""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_state_mgr:
            # Mock state manager
            mock_state_manager = Mock()
            mock_state_manager.is_fallback_active.return_value = False
            mock_state_mgr.return_value = mock_state_manager

            # Set fallback mode enabled
            config.CP_FALLBACK_MODE = True

            # Mock blocks.py imports to avoid importing the massive file
            with patch("index_core.blocks.CPBlocksPipeline") as mock_pipeline_class:
                mock_pipeline = Mock()
                mock_pipeline_class.return_value = mock_pipeline

                # Import and test the initialization logic
                from index_core import blocks

                # Simulate pipeline initialization call as it would happen in blocks.py
                start_block = 900000
                mock_pipeline_instance = CPBlocksPipeline(max_queue_size=200, fallback_mode=config.CP_FALLBACK_MODE)

                # Verify correct initialization
                assert mock_pipeline_instance.fallback_mode is True
                assert mock_pipeline_instance.state_manager is not None

    def test_pipeline_initialization_with_fallback_disabled(self):
        """Test pipeline initialization with fallback mode disabled"""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_state_mgr:
            # Set fallback mode disabled
            config.CP_FALLBACK_MODE = False

            # Create pipeline with fallback disabled
            mock_pipeline_instance = CPBlocksPipeline(max_queue_size=200, fallback_mode=config.CP_FALLBACK_MODE)

            # Verify fallback is disabled and no state manager
            assert mock_pipeline_instance.fallback_mode is False
            assert mock_pipeline_instance.state_manager is None
            mock_state_mgr.assert_not_called()

    def test_pipeline_reset_during_active_fallback(self):
        """Test pipeline reset behavior when fallback is active"""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_state_mgr:
            # Mock state manager with active fallback
            mock_state_manager = Mock()
            mock_state_manager.is_fallback_active.return_value = True
            mock_state_manager.get_fallback_start_block.return_value = 900000
            mock_state_manager.get_failed_blocks.return_value = {900001, 900002}
            mock_state_mgr.return_value = mock_state_manager

            # Create pipeline with active fallback state
            pipeline = CPBlocksPipeline(fallback_mode=True)

            # Verify pipeline loaded fallback state
            assert pipeline.fallback_started_at == 900000
            assert len(pipeline.failed_cp_blocks) == 2

            # Test reset operation (as would be called from blocks.py during rollback)
            reset_block = 899999
            pipeline.reset(reset_block)

            # Verify reset clears queue and updates current block
            assert len(pipeline.queue) == 0
            assert pipeline.current_block == reset_block

    def test_error_handling_with_fallback_mode_active(self):
        """Test error handling paths with fallback mode active"""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_state_mgr:
            mock_state_manager = Mock()
            mock_state_manager.is_fallback_active.return_value = False
            mock_state_mgr.return_value = mock_state_manager

            pipeline = CPBlocksPipeline(fallback_mode=True)
            pipeline.fallback_started_at = 900000

            # Mock CriticalBlockFetchError scenario
            from index_core.fetch_utils import CriticalBlockFetchError

            # Test that fallback mode handles critical errors gracefully
            test_block = 900001

            # In fallback mode, pipeline should create fallback block data
            fallback_data = pipeline.create_fallback_block(test_block)

            assert fallback_data is not None
            assert fallback_data["block_index"] == test_block
            assert fallback_data["fallback_mode"] is True
            assert fallback_data["needs_cp_reprocessing"] is True

    def test_pipeline_data_availability_during_fallback(self):
        """Test pipeline data availability checks with fallback mode"""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_state_mgr:
            mock_state_manager = Mock()
            mock_state_manager.is_fallback_active.return_value = False
            mock_state_mgr.return_value = mock_state_manager

            pipeline = CPBlocksPipeline(fallback_mode=True)

            # Simulate scenario where pipeline data is not available
            test_block = 900001
            pipeline.current_block = 900000

            # When block is not in queue, get_block should return None initially
            block_data = pipeline.get_block(test_block)
            assert block_data is None

            # But in fallback mode, we should be able to create fallback data
            pipeline.fallback_started_at = 900000
            fallback_data = pipeline.create_fallback_block(test_block)
            pipeline.failed_cp_blocks.add(test_block)

            assert fallback_data["fallback_mode"] is True

    def test_graceful_shutdown_with_active_fallback(self):
        """Test graceful shutdown with active fallback mode"""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_state_mgr:
            mock_state_manager = Mock()
            mock_state_manager.is_fallback_active.return_value = True
            mock_state_manager.get_fallback_start_block.return_value = 900000
            mock_state_manager.get_failed_blocks.return_value = {900001, 900002}
            mock_state_mgr.return_value = mock_state_manager

            pipeline = CPBlocksPipeline(fallback_mode=True)

            # Verify initial state loaded
            assert pipeline.fallback_started_at == 900000
            assert len(pipeline.failed_cp_blocks) == 2

            # Test shutdown process
            pipeline.shutdown()

            # Verify shutdown completed
            assert pipeline.shutdown_flag.is_set()
            assert pipeline.running is False

    def test_rollback_loop_detection_with_fallback(self):
        """Test rollback loop detection when fallback mode is active"""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_state_mgr:
            mock_state_manager = Mock()
            mock_state_manager.is_fallback_active.return_value = False
            mock_state_mgr.return_value = mock_state_manager

            pipeline = CPBlocksPipeline(fallback_mode=True)
            pipeline.fallback_started_at = 900000

            # Simulate multiple resets (as would happen during rollback loops)
            reset_block = 899999

            for i in range(3):
                pipeline.reset(reset_block)
                # Each reset should clear the queue
                assert len(pipeline.queue) == 0
                assert pipeline.current_block == reset_block

    def test_force_mode_interaction_with_fallback(self):
        """Test FORCE mode interaction with fallback mode"""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_state_mgr:
            mock_state_manager = Mock()
            mock_state_manager.is_fallback_active.return_value = False
            mock_state_mgr.return_value = mock_state_manager

            # Test with both FORCE and fallback enabled
            original_force = getattr(config, "FORCE", False)
            config.FORCE = True

            try:
                pipeline = CPBlocksPipeline(fallback_mode=True)

                # In this configuration, both error recovery mechanisms are active
                assert pipeline.fallback_mode is True
                assert config.FORCE is True

                # Pipeline should be able to create fallback data
                test_block = 900001
                pipeline.fallback_started_at = 900000
                fallback_data = pipeline.create_fallback_block(test_block)
                assert fallback_data["fallback_mode"] is True

            finally:
                config.FORCE = original_force


class TestBlocksFallbackHealthChecks:
    """Test CP node health check integration in blocks.py context"""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup method run before each test."""
        import index_core.fallback_state

        index_core.fallback_state._state_manager = None

    def teardown_method(self):
        """Cleanup method run after each test."""
        import index_core.fallback_state

        if index_core.fallback_state._state_manager:
            try:
                index_core.fallback_state._state_manager.cleanup_state_file()
            except:
                pass
            index_core.fallback_state._state_manager = None

    def test_health_check_during_block_processing(self):
        """Test CP node health checks during normal block processing"""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_state_mgr, patch(
            "index_core.pipeline_utils.get_healthy_nodes"
        ) as mock_get_nodes, patch("index_core.pipeline_utils.update_healthy_nodes") as mock_update_nodes:

            mock_state_manager = Mock()
            mock_state_manager.is_fallback_active.return_value = False
            mock_state_mgr.return_value = mock_state_manager

            pipeline = CPBlocksPipeline(fallback_mode=True)
            pipeline.fallback_started_at = 900000
            pipeline.failed_cp_blocks.add(900001)

            # Simulate healthy nodes becoming available
            pipeline.last_health_check = 0  # Force health check
            mock_get_nodes.return_value = [{"url": "http://healthy:4000", "name": "healthy"}]
            mock_update_nodes.return_value = None

            # Mock automatic rollback to prevent actual database operations
            with patch.object(pipeline, "_trigger_automatic_rollback") as mock_rollback:
                result = pipeline.check_cp_node_recovery()

                assert result is True
                mock_rollback.assert_called_once()

    def test_health_check_with_continued_failures(self):
        """Test health checks when nodes remain unhealthy"""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_state_mgr, patch(
            "index_core.pipeline_utils.get_healthy_nodes"
        ) as mock_get_nodes, patch("index_core.pipeline_utils.update_healthy_nodes") as mock_update_nodes:

            mock_state_manager = Mock()
            mock_state_manager.is_fallback_active.return_value = False
            mock_state_mgr.return_value = mock_state_manager

            pipeline = CPBlocksPipeline(fallback_mode=True)
            pipeline.fallback_started_at = 900000
            pipeline.failed_cp_blocks.add(900001)

            # Simulate continued node failures
            mock_get_nodes.return_value = []  # No healthy nodes
            mock_update_nodes.return_value = None

            result = pipeline.check_cp_node_recovery()
            assert result is False

            # Pipeline should continue in fallback mode
            assert pipeline.fallback_started_at == 900000
            assert len(pipeline.failed_cp_blocks) == 1


if __name__ == "__main__":
    pytest.main([__file__])
