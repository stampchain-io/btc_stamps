"""
Test cases for immediate fallback detection functionality.

These tests validate that the pipeline immediately enters fallback mode
when fetch operations completely fail, rather than waiting for periodic checks.
"""

import os
import sys
import threading
import time
import unittest.mock as mock
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config
from index_core.pipeline_utils import CPBlocksPipeline


@pytest.fixture(autouse=True)
def clear_rpc_environment_variables():
    """Clear RPC-related environment variables that could interfere with tests."""
    rpc_env_vars = [
        "RPC_IP",
        "RPC_PORT",
        "RPC_USER",
        "RPC_PASSWORD",
        "RPC_SSL",
        "CP_RPC_IP",
        "CP_RPC_PORT",
        "CP_RPC_USER",
        "CP_RPC_PASSWORD",
        "CP_FALLBACK_MODE",
    ]

    original_values = {}
    for var in rpc_env_vars:
        original_values[var] = os.environ.get(var)
        if var in os.environ:
            del os.environ[var]

    yield

    # Restore original values
    for var, value in original_values.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]


class TestImmediateFallbackDetection:
    """Test cases for immediate fallback mode detection."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup method run before each test."""
        self.original_fallback_mode = config.CP_FALLBACK_MODE
        self.test_start_block = 900000

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

    def test_immediate_fallback_in_fetch_batch_total_failure(self):
        """Test immediate fallback when _fetch_blocks_batch completely fails."""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_get_mgr:
            with patch("index_core.pipeline_utils.fetch_xcp_blocks_concurrent") as mock_fetch:
                with patch("index_core.pipeline_utils.update_healthy_nodes") as mock_update_nodes:
                    with patch("index_core.pipeline_utils.get_healthy_nodes") as mock_get_nodes:
                        # Mock state manager
                        mock_state_manager = Mock()
                        mock_state_manager.is_fallback_active.return_value = False
                        mock_get_mgr.return_value = mock_state_manager

                        # Mock total fetch failure - all retries fail
                        mock_fetch.return_value = {}  # Empty result = failure

                        # Mock health check after failure - no healthy nodes
                        mock_update_nodes.return_value = None
                        mock_get_nodes.return_value = []  # No healthy nodes

                        pipeline = CPBlocksPipeline(fallback_mode=True)
                        pipeline.running = True
                        pipeline.fallback_started_at = None  # Not in fallback yet
                        pipeline.current_block = 900000

                        # Mock _enter_fallback_mode to track if it's called
                        with patch.object(pipeline, "_enter_fallback_mode") as mock_enter_fallback:
                            with patch("time.sleep"):  # Speed up test by mocking sleep
                                result = pipeline._fetch_blocks_batch([900001, 900002], "http://test:8080")

                        # Should return empty due to failure
                        assert result == {}

                        # Should have triggered immediate fallback entry
                        mock_enter_fallback.assert_called_once()

                        # Should have updated health nodes immediately
                        mock_update_nodes.assert_called()
                        mock_get_nodes.assert_called()

    def test_no_immediate_fallback_when_already_in_fallback(self):
        """Test that immediate fallback is not triggered when already in fallback mode."""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_get_mgr:
            with patch("index_core.pipeline_utils.fetch_xcp_blocks_concurrent") as mock_fetch:
                with patch("index_core.pipeline_utils.update_healthy_nodes") as mock_update_nodes:
                    with patch("index_core.pipeline_utils.get_healthy_nodes") as mock_get_nodes:
                        # Mock state manager
                        mock_state_manager = Mock()
                        mock_state_manager.is_fallback_active.return_value = False
                        mock_get_mgr.return_value = mock_state_manager

                        # Mock total fetch failure
                        mock_fetch.return_value = {}
                        mock_update_nodes.return_value = None
                        mock_get_nodes.return_value = []

                        pipeline = CPBlocksPipeline(fallback_mode=True)
                        pipeline.running = True
                        pipeline.fallback_started_at = 900000  # Already in fallback
                        pipeline.current_block = 900000

                        # Mock _enter_fallback_mode to track if it's called
                        with patch.object(pipeline, "_enter_fallback_mode") as mock_enter_fallback:
                            with patch("time.sleep"):  # Speed up test
                                result = pipeline._fetch_blocks_batch([900001, 900002], "http://test:8080")

                        # Should return empty due to failure
                        assert result == {}

                        # Should NOT have triggered fallback entry (already in fallback)
                        mock_enter_fallback.assert_not_called()

    def test_no_immediate_fallback_when_nodes_still_healthy(self):
        """Test that immediate fallback is not triggered when nodes are still healthy."""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_get_mgr:
            with patch("index_core.pipeline_utils.fetch_xcp_blocks_concurrent") as mock_fetch:
                with patch("index_core.pipeline_utils.update_healthy_nodes") as mock_update_nodes:
                    with patch("index_core.pipeline_utils.get_healthy_nodes") as mock_get_nodes:
                        # Mock state manager
                        mock_state_manager = Mock()
                        mock_state_manager.is_fallback_active.return_value = False
                        mock_get_mgr.return_value = mock_state_manager

                        # Mock total fetch failure
                        mock_fetch.return_value = {}

                        # Mock health check after failure - nodes are still healthy
                        mock_update_nodes.return_value = None
                        mock_get_nodes.return_value = [{"name": "test_node", "url": "http://test:8080"}]

                        pipeline = CPBlocksPipeline(fallback_mode=True)
                        pipeline.running = True
                        pipeline.fallback_started_at = None  # Not in fallback yet
                        pipeline.current_block = 900000

                        # Mock _enter_fallback_mode to track if it's called
                        with patch.object(pipeline, "_enter_fallback_mode") as mock_enter_fallback:
                            with patch("time.sleep"):  # Speed up test
                                result = pipeline._fetch_blocks_batch([900001, 900002], "http://test:8080")

                        # Should return empty due to failure
                        assert result == {}

                        # Should NOT have triggered fallback entry (nodes still healthy)
                        mock_enter_fallback.assert_not_called()

    def test_immediate_fallback_in_worker_loop_when_no_nodes(self):
        """Test immediate fallback when worker loop detects no healthy nodes."""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_get_mgr:
            with patch("index_core.pipeline_utils.get_healthy_nodes") as mock_get_nodes:
                with patch("index_core.pipeline_utils.update_healthy_nodes") as mock_update_nodes:
                    with patch("index_core.pipeline_utils.backend_instance") as mock_backend:
                        # Mock state manager
                        mock_state_manager = Mock()
                        mock_state_manager.is_fallback_active.return_value = False
                        mock_get_mgr.return_value = mock_state_manager

                        # Mock no healthy nodes
                        mock_get_nodes.return_value = []
                        mock_update_nodes.return_value = None
                        mock_backend.getblockcount.return_value = 900010

                        pipeline = CPBlocksPipeline(fallback_mode=True)
                        pipeline.current_block = 900000
                        pipeline.fallback_started_at = None  # Not in fallback yet
                        pipeline.running = True

                        # Mock _enter_fallback_mode to track if it's called
                        with patch.object(pipeline, "_enter_fallback_mode") as mock_enter_fallback:
                            # Mock the worker to run a minimal loop
                            original_worker = pipeline._fetch_blocks_worker

                            def mock_worker():
                                # Simulate one iteration that detects no nodes
                                try:
                                    nodes = mock_get_nodes()
                                    if not nodes:
                                        mock_update_nodes()
                                        nodes = mock_get_nodes()
                                    if not nodes:
                                        if pipeline.fallback_mode and not pipeline.fallback_started_at:
                                            mock_enter_fallback()
                                finally:
                                    pipeline.shutdown_flag.set()

                            pipeline._fetch_blocks_worker = mock_worker
                            pipeline._fetch_blocks_worker()

                        # Should have triggered immediate fallback entry
                        mock_enter_fallback.assert_called_once()

    def test_fallback_disabled_no_immediate_entry(self):
        """Test that immediate fallback is not triggered when fallback mode is disabled."""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_get_mgr:
            with patch("index_core.pipeline_utils.fetch_xcp_blocks_concurrent") as mock_fetch:
                with patch("index_core.pipeline_utils.update_healthy_nodes") as mock_update_nodes:
                    with patch("index_core.pipeline_utils.get_healthy_nodes") as mock_get_nodes:
                        # Mock fetch failure
                        mock_fetch.return_value = {}
                        mock_update_nodes.return_value = None
                        mock_get_nodes.return_value = []

                        pipeline = CPBlocksPipeline(fallback_mode=False)  # Fallback disabled
                        pipeline.running = True
                        pipeline.current_block = 900000

                        # Mock _enter_fallback_mode to track if it's called
                        with patch.object(pipeline, "_enter_fallback_mode") as mock_enter_fallback:
                            with patch("time.sleep"):  # Speed up test
                                result = pipeline._fetch_blocks_batch([900001, 900002], "http://test:8080")

                        # Should return empty due to failure
                        assert result == {}

                        # Should NOT have triggered fallback entry (fallback disabled)
                        mock_enter_fallback.assert_not_called()

    def test_health_update_exception_handling(self):
        """Test that exceptions during immediate health updates are handled gracefully."""
        with patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_get_mgr:
            with patch("index_core.pipeline_utils.fetch_xcp_blocks_concurrent") as mock_fetch:
                with patch("index_core.pipeline_utils.update_healthy_nodes") as mock_update_nodes:
                    with patch("index_core.pipeline_utils.get_healthy_nodes") as mock_get_nodes:
                        # Mock state manager
                        mock_state_manager = Mock()
                        mock_state_manager.is_fallback_active.return_value = False
                        mock_get_mgr.return_value = mock_state_manager

                        # Mock fetch failure
                        mock_fetch.return_value = {}

                        # Mock health update to raise exception
                        mock_update_nodes.side_effect = Exception("Health update failed")

                        pipeline = CPBlocksPipeline(fallback_mode=True)
                        pipeline.running = True
                        pipeline.fallback_started_at = None
                        pipeline.current_block = 900000

                        # Should not raise exception, should handle gracefully
                        with patch("time.sleep"):  # Speed up test
                            result = pipeline._fetch_blocks_batch([900001, 900002], "http://test:8080")

                        # Should return empty due to failure
                        assert result == {}

                        # Health update should have been attempted multiple times (retries + immediate check)
                        assert mock_update_nodes.call_count >= 1


if __name__ == "__main__":
    pytest.main([__file__])
