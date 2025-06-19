"""
Test the enhanced node failover mechanism for handling persistent timeouts and connection issues.

This test verifies that:
1. Timeout failures are escalated to severe failures after multiple occurrences
2. Progressive backoff is applied for minor failures
3. Nodes with persistent issues are excluded from healthy nodes list
4. Automatic health updates are triggered when needed
"""

import time
import unittest
from unittest.mock import MagicMock, patch

import index_core.node_health as node_health_module
from index_core.node_health import (
    NodeHealth,
    clear_shutdown_flag,
    get_healthy_nodes,
    healthy_nodes_lock,
    update_healthy_nodes,
)


class TestEnhancedNodeFailover(unittest.TestCase):
    """Test enhanced node failover mechanism."""

    def setUp(self):
        """Set up test environment."""
        clear_shutdown_flag()

        # Clear global state
        with healthy_nodes_lock:
            node_health_module.healthy_nodes.clear()
        node_health_module.node_health_tracker.clear()

    def tearDown(self):
        """Clean up after tests."""
        # Clear global state
        with healthy_nodes_lock:
            node_health_module.healthy_nodes.clear()
        node_health_module.node_health_tracker.clear()

    def test_timeout_escalation_to_severe_failure(self):
        """Test that timeouts escalate to severe failures after multiple occurrences."""
        node = NodeHealth("test-node", "http://test:4000/v2")

        # First few timeouts should be minor failures
        node.mark_failure("Timeout during session.get")
        self.assertEqual(node.consecutive_failures, 0)
        self.assertEqual(node.minor_failures, 1)

        node.mark_failure("Timeout during session.get")
        self.assertEqual(node.consecutive_failures, 0)
        self.assertEqual(node.minor_failures, 2)

        node.mark_failure("Timeout during session.get")
        self.assertEqual(node.consecutive_failures, 0)
        self.assertEqual(node.minor_failures, 3)

        # Fourth timeout should escalate to severe failure
        node.mark_failure("Timeout during session.get")
        self.assertEqual(node.consecutive_failures, 1)  # Now it's a severe failure
        self.assertTrue(node.backoff_until > time.time())  # Should be in backoff
        self.assertFalse(node.healthy)  # Should not be healthy

    def test_progressive_backoff_for_minor_failures(self):
        """Test that minor failures get progressive backoff periods."""
        node = NodeHealth("test-node", "http://test:4000/v2")
        current_time = time.time()

        # First two minor failures should not trigger backoff
        node.mark_failure("Timeout during session.get")
        node.mark_failure("Timeout during session.get")
        self.assertEqual(node.backoff_until, 0)

        # Third minor failure should trigger progressive backoff
        node.mark_failure("Timeout during session.get")
        self.assertGreater(node.backoff_until, current_time)
        # The third failure triggers a 10-second backoff: 5 * (3-2) * 2 = 10
        self.assertLessEqual(node.backoff_until - current_time, 12)  # Allow some tolerance

        # Reset for next test
        current_time = time.time()
        node.backoff_until = 0

        # Simulate more failures to test progressive backoff
        # Use non-escalating 404 errors to stay in minor failure mode
        node.minor_failures = 4
        node.mark_failure("404 Block not yet processed by XCP")
        backoff_duration = node.backoff_until - current_time
        # 5th failure: 5 * (5-2) * 2 = 30 seconds
        self.assertGreater(backoff_duration, 25)  # Should be around 30 seconds

    def test_connection_error_escalation(self):
        """Test that connection errors escalate to severe failures after 2 occurrences."""
        node = NodeHealth("test-node", "http://test:4000/v2")

        # First connection error should be minor
        node.mark_failure("Connection error")
        self.assertEqual(node.consecutive_failures, 0)
        self.assertEqual(node.minor_failures, 1)

        # Second connection error should be minor
        node.mark_failure("Connection error")
        self.assertEqual(node.consecutive_failures, 0)
        self.assertEqual(node.minor_failures, 2)

        # Third connection error should escalate to severe
        node.mark_failure("Connection error")
        self.assertEqual(node.consecutive_failures, 1)

    def test_healthy_nodes_filtering(self):
        """Test that get_healthy_nodes() properly filters out problematic nodes."""
        # Set up mock config nodes
        mock_nodes = [
            {"name": "healthy-node", "url": "http://healthy:4000/v2"},
            {"name": "timeout-node", "url": "http://timeout:4000/v2"},
            {"name": "backoff-node", "url": "http://backoff:4000/v2"},
        ]

        # Create node health trackers
        healthy_node = NodeHealth("healthy-node", "http://healthy:4000/v2")
        timeout_node = NodeHealth("timeout-node", "http://timeout:4000/v2")
        backoff_node = NodeHealth("backoff-node", "http://backoff:4000/v2")

        # Simulate failures
        for _ in range(6):  # Enough to trigger exclusion
            timeout_node.mark_failure("Timeout during session.get")

        backoff_node.mark_failure("Connection error")  # Severe failure, puts in backoff
        backoff_node.mark_failure("Connection error")
        backoff_node.mark_failure("Connection error")

        # Update global trackers
        node_health_module.node_health_tracker["healthy-node"] = healthy_node
        node_health_module.node_health_tracker["timeout-node"] = timeout_node
        node_health_module.node_health_tracker["backoff-node"] = backoff_node

        # Set up healthy nodes list (normally set by update_healthy_nodes)
        with healthy_nodes_lock:
            node_health_module.healthy_nodes.extend(mock_nodes)

        # Get healthy nodes should filter out problematic ones
        result = get_healthy_nodes()

        # Should only return the healthy node
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "healthy-node")

    @patch(
        "index_core.node_health.config.XCP_V2_NODES",
        [
            {"name": "good-node", "url": "http://good:4000/v2"},
            {"name": "bad-node", "url": "http://bad:4000/v2"},
        ],
    )
    @patch("requests.get")
    def test_update_healthy_nodes_excludes_persistent_failures(self, mock_get):
        """Test that update_healthy_nodes excludes nodes with persistent failures."""

        # Create node with persistent failures (3+ to trigger exclusion)
        bad_node = NodeHealth("bad-node", "http://bad:4000/v2")
        bad_node.consecutive_failures = 3  # Has enough consecutive failures to be excluded
        node_health_module.node_health_tracker["bad-node"] = bad_node

        # Mock successful health checks for both
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": {"status": "Healthy"}}
        mock_get.return_value = mock_response

        # Update health
        success = update_healthy_nodes()

        # Should succeed but exclude the bad node
        self.assertTrue(success)
        with healthy_nodes_lock:
            healthy_node_names = [node["name"] for node in node_health_module.healthy_nodes]

        # Bad node should be excluded despite passing health check
        self.assertIn("good-node", healthy_node_names)
        self.assertNotIn("bad-node", healthy_node_names)

    def test_node_recovery_after_success(self):
        """Test that nodes can recover after successful operations."""
        node = NodeHealth("test-node", "http://test:4000/v2")

        # Simulate failures
        for _ in range(5):
            node.mark_failure("Timeout during session.get")

        # Node should be unhealthy
        self.assertFalse(node.healthy)
        self.assertGreater(node.minor_failures, 0)

        # Mark success should reset failures
        node.mark_success()

        # Node should be healthy again
        self.assertTrue(node.healthy)
        self.assertEqual(node.consecutive_failures, 0)
        self.assertEqual(node.minor_failures, 0)
        self.assertEqual(node.backoff_until, 0)

    @patch("index_core.node_health.threading.Thread")
    def test_automatic_health_update_trigger(self, mock_thread):
        """Test that persistent failures trigger automatic health updates."""
        node = NodeHealth("test-node", "http://test:4000/v2")

        # Mock the thread start method
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        # Use specific 404 pattern that's treated as minor failure
        error_msg = "404 Block not yet processed by XCP"

        # Simulate 5 minor failures to trigger the health update
        for i in range(5):
            node.mark_failure(error_msg)

        # Should have triggered a health update thread
        mock_thread.assert_called_with(target=update_healthy_nodes, daemon=True)
        mock_thread_instance.start.assert_called_once()

    def test_can_retry_logic(self):
        """Test the can_retry logic for nodes in backoff."""
        node = NodeHealth("test-node", "http://test:4000/v2")

        # Initially should be able to retry
        self.assertTrue(node.can_retry())

        # Put node in backoff
        node.backoff_until = time.time() + 10  # 10 seconds in future

        # Should not be able to retry
        self.assertFalse(node.can_retry())

        # Set backoff in the past
        node.backoff_until = time.time() - 1

        # Should be able to retry again
        self.assertTrue(node.can_retry())


if __name__ == "__main__":
    unittest.main()
