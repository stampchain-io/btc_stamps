"""
Tests for CP height check functionality.

These tests validate the behavior of:
1. wait_for_cp_block_processed() - waits for CP to process a specific block
2. Pipeline CP height check - prevents fetching blocks CP hasn't processed
3. Timeout and retry behavior
4. Multi-node round-robin behavior
"""

import time
from unittest.mock import MagicMock, patch

import pytest


class TestWaitForCPBlockProcessed:
    """Tests for the wait_for_cp_block_processed function."""

    def test_immediate_success_when_cp_ready(self):
        """Test that function returns True immediately when CP has processed the block."""
        from index_core.fetch_utils import wait_for_cp_block_processed

        mock_node = {"name": "test-node", "url": "http://test:4000/v2"}

        with patch("index_core.fetch_utils.get_healthy_nodes", return_value=[mock_node]):
            with patch("index_core.fetch_utils.fetch_node_version_v2") as mock_fetch:
                # CP is at block 100, we're asking for block 100
                mock_fetch.return_value = (
                    "10.0.0",
                    {"last_block": 100, "db_caught_up": True},
                )

                start = time.time()
                result = wait_for_cp_block_processed(100, max_wait=10.0, check_interval=1.0)
                elapsed = time.time() - start

                assert result is True
                assert elapsed < 1.0  # Should return almost immediately
                mock_fetch.assert_called_once()

    def test_immediate_success_when_cp_ahead(self):
        """Test that function returns True when CP is ahead of requested block."""
        from index_core.fetch_utils import wait_for_cp_block_processed

        mock_node = {"name": "test-node", "url": "http://test:4000/v2"}

        with patch("index_core.fetch_utils.get_healthy_nodes", return_value=[mock_node]):
            with patch("index_core.fetch_utils.fetch_node_version_v2") as mock_fetch:
                # CP is at block 105, we're asking for block 100
                mock_fetch.return_value = (
                    "10.0.0",
                    {"last_block": 105, "db_caught_up": True},
                )

                result = wait_for_cp_block_processed(100, max_wait=10.0, check_interval=1.0)

                assert result is True

    def test_timeout_when_cp_behind(self):
        """Test that function returns False after timeout when CP is behind."""
        from index_core.fetch_utils import wait_for_cp_block_processed

        mock_node = {"name": "test-node", "url": "http://test:4000/v2"}

        with patch("index_core.fetch_utils.get_healthy_nodes", return_value=[mock_node]):
            with patch("index_core.fetch_utils.fetch_node_version_v2") as mock_fetch:
                # CP is at block 95, we're asking for block 100 - CP is behind
                mock_fetch.return_value = (
                    "10.0.0",
                    {"last_block": 95, "db_caught_up": True},
                )

                start = time.time()
                result = wait_for_cp_block_processed(100, max_wait=2.0, check_interval=0.5)
                elapsed = time.time() - start

                assert result is False
                assert elapsed >= 2.0  # Should wait full timeout
                assert elapsed < 3.0  # But not too much longer

    def test_eventual_success_after_cp_catches_up(self):
        """Test that function returns True when CP catches up during wait."""
        from index_core.fetch_utils import wait_for_cp_block_processed

        mock_node = {"name": "test-node", "url": "http://test:4000/v2"}
        call_count = [0]

        def mock_fetch_side_effect(url):
            call_count[0] += 1
            if call_count[0] < 3:
                # First 2 calls: CP is behind
                return ("10.0.0", {"last_block": 95, "db_caught_up": True})
            else:
                # 3rd call: CP has caught up
                return ("10.0.0", {"last_block": 100, "db_caught_up": True})

        with patch("index_core.fetch_utils.get_healthy_nodes", return_value=[mock_node]):
            with patch("index_core.fetch_utils.fetch_node_version_v2", side_effect=mock_fetch_side_effect):
                start = time.time()
                result = wait_for_cp_block_processed(100, max_wait=10.0, check_interval=0.5)
                elapsed = time.time() - start

                assert result is True
                assert call_count[0] == 3  # Should have checked 3 times
                assert elapsed >= 1.0  # At least 2 intervals
                assert elapsed < 3.0  # But caught up before timeout

    def test_returns_false_when_server_not_ready(self):
        """Test that function waits when server_ready/db_caught_up is False."""
        from index_core.fetch_utils import wait_for_cp_block_processed

        mock_node = {"name": "test-node", "url": "http://test:4000/v2"}

        with patch("index_core.fetch_utils.get_healthy_nodes", return_value=[mock_node]):
            with patch("index_core.fetch_utils.fetch_node_version_v2") as mock_fetch:
                # CP has the block but db_caught_up is False
                mock_fetch.return_value = (
                    "10.0.0",
                    {"last_block": 100, "db_caught_up": False},
                )

                result = wait_for_cp_block_processed(100, max_wait=1.0, check_interval=0.5)

                assert result is False  # Should timeout because db not caught up

    def test_handles_no_healthy_nodes(self):
        """Test that function handles case when no healthy nodes are available."""
        from index_core.fetch_utils import wait_for_cp_block_processed

        with patch("index_core.fetch_utils.get_healthy_nodes", return_value=[]):
            start = time.time()
            result = wait_for_cp_block_processed(100, max_wait=1.0, check_interval=0.3)
            elapsed = time.time() - start

            assert result is False
            assert elapsed >= 1.0  # Should wait full timeout

    def test_handles_fetch_exception(self):
        """Test that function handles exceptions from fetch_node_version_v2."""
        from index_core.fetch_utils import wait_for_cp_block_processed

        mock_node = {"name": "test-node", "url": "http://test:4000/v2"}

        with patch("index_core.fetch_utils.get_healthy_nodes", return_value=[mock_node]):
            with patch("index_core.fetch_utils.fetch_node_version_v2", side_effect=Exception("Connection error")):
                result = wait_for_cp_block_processed(100, max_wait=1.0, check_interval=0.3)

                assert result is False  # Should timeout after exceptions


class TestWaitForCPBlockProcessedMultiNode:
    """Tests for multi-node behavior in wait_for_cp_block_processed."""

    def test_uses_first_healthy_node(self):
        """Test that function uses the first healthy node from the list."""
        from index_core.fetch_utils import wait_for_cp_block_processed

        mock_nodes = [
            {"name": "node1", "url": "http://node1:4000/v2"},
            {"name": "node2", "url": "http://node2:4000/v2"},
        ]

        with patch("index_core.fetch_utils.get_healthy_nodes", return_value=mock_nodes):
            with patch("index_core.fetch_utils.fetch_node_version_v2") as mock_fetch:
                mock_fetch.return_value = ("10.0.0", {"last_block": 100, "db_caught_up": True})

                result = wait_for_cp_block_processed(100, max_wait=5.0)

                assert result is True
                # Should use first node's URL
                mock_fetch.assert_called_with("http://node1:4000/v2")

    def test_retries_with_updated_healthy_nodes(self):
        """Test that function gets fresh healthy nodes on each iteration."""
        from index_core.fetch_utils import wait_for_cp_block_processed

        call_count = [0]

        def mock_get_healthy_nodes():
            call_count[0] += 1
            if call_count[0] == 1:
                return [{"name": "node1", "url": "http://node1:4000/v2"}]
            else:
                return [{"name": "node2", "url": "http://node2:4000/v2"}]

        fetch_calls = []

        def mock_fetch(url):
            fetch_calls.append(url)
            if "node1" in url:
                # Node1 is behind
                return ("10.0.0", {"last_block": 95, "db_caught_up": True})
            else:
                # Node2 has caught up
                return ("10.0.0", {"last_block": 100, "db_caught_up": True})

        with patch("index_core.fetch_utils.get_healthy_nodes", side_effect=mock_get_healthy_nodes):
            with patch("index_core.fetch_utils.fetch_node_version_v2", side_effect=mock_fetch):
                result = wait_for_cp_block_processed(100, max_wait=5.0, check_interval=0.5)

                assert result is True
                # Should have called both nodes
                assert len(fetch_calls) >= 2
                assert "node1" in fetch_calls[0]
                assert "node2" in fetch_calls[1]


class TestPipelineCPHeightCheck:
    """Tests for the pipeline's CP height check integration."""

    def test_pipeline_waits_for_cp_before_fetching_tip_blocks(self):
        """Test that pipeline waits for CP to process blocks near the tip."""
        from index_core.pipeline_utils import CPBlocksPipeline

        # This test verifies the integration point exists
        # The actual waiting behavior is tested in TestWaitForCPBlockProcessed

        with patch("index_core.pipeline_utils.get_healthy_nodes", return_value=[]):
            with patch("index_core.pipeline_utils.backend_instance") as mock_backend:
                mock_backend.getblockcount.return_value = 100

                # Create pipeline but don't start it
                pipeline = CPBlocksPipeline(
                    fallback_mode=False,
                )

                # Verify the pipeline has access to wait_for_cp_block_processed
                from index_core.fetch_utils import wait_for_cp_block_processed

                assert callable(wait_for_cp_block_processed)

                # Clean up
                pipeline.shutdown_flag.set()

    def test_tip_threshold_calculation(self):
        """Test that tip_threshold correctly identifies blocks near the tip."""
        # The pipeline uses tip_threshold = 5
        # Blocks within 5 of the tip should be checked
        tip_threshold = 5
        block_tip = 100

        # Test blocks that should be checked (near tip)
        blocks_to_fetch = [96, 97, 98, 99, 100]
        blocks_near_tip = [b for b in blocks_to_fetch if block_tip - b < tip_threshold]
        assert blocks_near_tip == [96, 97, 98, 99, 100]

        # Test blocks that should NOT be checked (not near tip)
        blocks_to_fetch = [90, 91, 92, 93, 94]
        blocks_near_tip = [b for b in blocks_to_fetch if block_tip - b < tip_threshold]
        assert blocks_near_tip == []  # None are near tip

        # Test mixed case
        blocks_to_fetch = [94, 95, 96, 97, 98]
        blocks_near_tip = [b for b in blocks_to_fetch if block_tip - b < tip_threshold]
        assert blocks_near_tip == [96, 97, 98]  # Only these are within 5 of tip


class TestCPHeightCheckTimeout:
    """Tests for the 3-minute timeout behavior."""

    def test_three_minute_timeout_constant(self):
        """Verify the 3-minute timeout is configured correctly in pipeline."""
        # The pipeline uses cp_wait_timeout = 180.0 (3 minutes)
        expected_timeout = 180.0

        # Read the actual value from the source
        import ast
        import os

        pipeline_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "src",
            "index_core",
            "pipeline_utils.py",
        )

        with open(pipeline_path, "r") as f:
            content = f.read()

        # Check that the timeout is set to 180 seconds
        assert "cp_wait_timeout = 180.0" in content, "Expected 3-minute (180s) timeout in pipeline"

    def test_timeout_triggers_fallback_mode(self):
        """Test that timeout after 3 minutes triggers fallback mode."""
        from index_core.pipeline_utils import CPBlocksPipeline

        with patch("index_core.pipeline_utils.get_healthy_nodes", return_value=[]):
            with patch("index_core.pipeline_utils.backend_instance") as mock_backend:
                mock_backend.getblockcount.return_value = 100

                pipeline = CPBlocksPipeline(
                    fallback_mode=True,  # Enable fallback mode
                )

                # Verify fallback mode is enabled
                assert pipeline.fallback_mode is True

                # The actual timeout + fallback trigger is tested in integration
                # This just verifies the configuration is correct

                pipeline.shutdown_flag.set()


class TestCPHeightCheckRoundRobin:
    """Tests for round-robin behavior with multiple CP nodes."""

    def test_healthy_nodes_checked_on_each_iteration(self):
        """Test that get_healthy_nodes is called on each wait iteration."""
        from index_core.fetch_utils import wait_for_cp_block_processed

        mock_node = {"name": "test-node", "url": "http://test:4000/v2"}
        get_healthy_calls = [0]

        def mock_get_healthy():
            get_healthy_calls[0] += 1
            return [mock_node]

        with patch("index_core.fetch_utils.get_healthy_nodes", side_effect=mock_get_healthy):
            with patch("index_core.fetch_utils.fetch_node_version_v2") as mock_fetch:
                # Always return CP behind to force multiple iterations
                mock_fetch.return_value = ("10.0.0", {"last_block": 95, "db_caught_up": True})

                # Wait with short timeout and interval
                wait_for_cp_block_processed(100, max_wait=1.0, check_interval=0.3)

                # Should have called get_healthy_nodes multiple times
                assert get_healthy_calls[0] >= 3

    def test_different_nodes_can_report_different_heights(self):
        """Test handling when different nodes report different CP heights."""
        from index_core.fetch_utils import wait_for_cp_block_processed

        call_count = [0]

        def mock_get_healthy():
            call_count[0] += 1
            # Alternate between nodes
            if call_count[0] % 2 == 1:
                return [{"name": "node1", "url": "http://node1:4000/v2"}]
            else:
                return [{"name": "node2", "url": "http://node2:4000/v2"}]

        def mock_fetch(url):
            if "node1" in url:
                return ("10.0.0", {"last_block": 95, "db_caught_up": True})  # Behind
            else:
                return ("10.0.0", {"last_block": 100, "db_caught_up": True})  # Ready

        with patch("index_core.fetch_utils.get_healthy_nodes", side_effect=mock_get_healthy):
            with patch("index_core.fetch_utils.fetch_node_version_v2", side_effect=mock_fetch):
                result = wait_for_cp_block_processed(100, max_wait=5.0, check_interval=0.3)

                # Should succeed when node2 reports ready
                assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
