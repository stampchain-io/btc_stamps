"""
Tests for node_health module
============================

Tests for shutdown callbacks, node health tracking, and API monitoring functionality.
"""

import logging
import threading
import time
import unittest
from unittest.mock import MagicMock, Mock, patch

import pytest

from index_core.node_health import (
    NodeHealth,
    clear_shutdown_flag,
    is_shutdown_requested,
    register_shutdown_callback,
    set_shutdown_flag,
    unregister_shutdown_callback,
)


class TestShutdownCallbacks(unittest.TestCase):
    """Test shutdown callback registration and execution."""

    def setUp(self):
        """Clear shutdown flag before each test."""
        clear_shutdown_flag()
        # Clear any existing callbacks
        import index_core.node_health

        index_core.node_health._shutdown_callbacks = []

    def tearDown(self):
        """Clean up after tests."""
        clear_shutdown_flag()
        import index_core.node_health

        index_core.node_health._shutdown_callbacks = []

    def test_register_and_execute_callback(self):
        """Test registering and executing shutdown callbacks."""
        callback_executed = False

        def test_callback():
            nonlocal callback_executed
            callback_executed = True

        # Register callback
        register_shutdown_callback(test_callback)

        # Trigger shutdown
        set_shutdown_flag()

        # Verify callback was executed
        self.assertTrue(callback_executed)
        self.assertTrue(is_shutdown_requested())

    def test_multiple_callbacks(self):
        """Test registering multiple callbacks."""
        results = []

        def callback1():
            results.append(1)

        def callback2():
            results.append(2)

        def callback3():
            results.append(3)

        # Register multiple callbacks
        register_shutdown_callback(callback1)
        register_shutdown_callback(callback2)
        register_shutdown_callback(callback3)

        # Trigger shutdown
        set_shutdown_flag()

        # All callbacks should execute
        self.assertEqual(sorted(results), [1, 2, 3])

    def test_duplicate_callback_registration(self):
        """Test that duplicate callbacks are not registered twice."""
        call_count = 0

        def test_callback():
            nonlocal call_count
            call_count += 1

        # Register the same callback twice
        register_shutdown_callback(test_callback)
        register_shutdown_callback(test_callback)

        # Trigger shutdown
        set_shutdown_flag()

        # Should only be called once
        self.assertEqual(call_count, 1)

    def test_unregister_callback(self):
        """Test unregistering callbacks."""
        callback_executed = False

        def test_callback():
            nonlocal callback_executed
            callback_executed = True

        # Register then unregister
        register_shutdown_callback(test_callback)
        unregister_shutdown_callback(test_callback)

        # Trigger shutdown
        set_shutdown_flag()

        # Callback should not execute
        self.assertFalse(callback_executed)

    def test_callback_exception_handling(self):
        """Test that exceptions in callbacks don't stop other callbacks."""
        results = []

        def failing_callback():
            results.append("failing")
            raise Exception("Test exception")

        def successful_callback():
            results.append("successful")

        # Register callbacks
        register_shutdown_callback(failing_callback)
        register_shutdown_callback(successful_callback)

        # Trigger shutdown - should not raise
        set_shutdown_flag()

        # Both callbacks should have been attempted
        self.assertIn("failing", results)
        self.assertIn("successful", results)

    def test_late_callback_registration(self):
        """Test registering a callback after shutdown has been requested."""
        callback_executed = False

        def late_callback():
            nonlocal callback_executed
            callback_executed = True

        # Trigger shutdown first
        set_shutdown_flag()

        # Register callback after shutdown
        register_shutdown_callback(late_callback)

        # Callback should execute immediately
        self.assertTrue(callback_executed)

    def test_clear_shutdown_flag(self):
        """Test clearing the shutdown flag."""
        # Set and then clear
        set_shutdown_flag()
        self.assertTrue(is_shutdown_requested())

        clear_shutdown_flag()
        self.assertFalse(is_shutdown_requested())


class TestNodeHealth(unittest.TestCase):
    """Test NodeHealth class functionality."""

    def test_node_health_initialization(self):
        """Test NodeHealth initialization."""
        node = NodeHealth("test-node", "http://test.com")

        self.assertEqual(node.name, "test-node")
        self.assertEqual(node.url, "http://test.com")
        self.assertEqual(node.failures, 0)
        self.assertEqual(node.consecutive_failures, 0)
        self.assertEqual(node.last_failure_time, 0.0)
        self.assertEqual(node.backoff_until, 0.0)
        self.assertIsNone(node.version)

    @patch("index_core.node_health.exponential_backoff", return_value=10.0)
    def test_mark_failure(self, mock_backoff):
        """Test marking node failures."""
        node = NodeHealth("test-node", "http://test.com")

        # Mark first failure with a severe error
        with patch("time.time", return_value=1000.0):
            node.mark_failure("Internal server error")

        self.assertEqual(node.failures, 1)
        self.assertEqual(node.consecutive_failures, 1)
        self.assertEqual(node.last_failure_time, 1000.0)
        self.assertEqual(node.backoff_until, 1010.0)  # 1000 + 10 from mock

    def test_mark_minor_failure(self):
        """Test marking minor node failures."""
        node = NodeHealth("test-node", "http://test.com")

        # Mark minor failures (connection errors are not severe)
        with patch("time.time", return_value=1000.0):
            node.mark_failure("Connection error")

        self.assertEqual(node.failures, 1)
        self.assertEqual(node.consecutive_failures, 0)  # Minor failures don't increment this
        self.assertEqual(node.minor_failures, 1)
        self.assertEqual(node.backoff_until, 0)  # No backoff for single minor failure

    def test_mark_success(self):
        """Test marking node success."""
        node = NodeHealth("test-node", "http://test.com")

        # Set up some failures
        node.failures = 5
        node.consecutive_failures = 3
        node.backoff_until = 2000.0

        # Mark success
        node.mark_success()

        # Consecutive failures should reset
        self.assertEqual(node.consecutive_failures, 0)
        self.assertEqual(node.backoff_until, 0)
        # Total failures remain
        self.assertEqual(node.failures, 5)

    def test_can_retry(self):
        """Test node retry availability check."""
        node = NodeHealth("test-node", "http://test.com")

        # Should be able to retry initially
        self.assertTrue(node.can_retry())

        # Set backoff in future
        with patch("time.time", return_value=1000.0):
            node.backoff_until = 2000.0
            self.assertFalse(node.can_retry())

        # Backoff expired
        with patch("time.time", return_value=3000.0):
            self.assertTrue(node.can_retry())

    def test_is_severe_failure(self):
        """Test determining if a failure is severe."""
        node = NodeHealth("test-node", "http://test.com")

        # 404 for recent blocks should not be severe
        self.assertFalse(node.is_severe_failure("404 - Block not yet processed by XCP"))

        # Connection errors are not severe
        self.assertFalse(node.is_severe_failure("Connection timeout"))

        # Other errors are severe
        self.assertTrue(node.is_severe_failure("Internal server error"))

    def test_healthy_property(self):
        """Test the healthy property."""
        node = NodeHealth("test-node", "http://test.com")

        # Should be healthy initially
        self.assertTrue(node.healthy)

        # Not healthy with consecutive failures
        node.consecutive_failures = 2
        self.assertFalse(node.healthy)

        # Not healthy when in backoff
        node.consecutive_failures = 0
        with patch("time.time", return_value=1000.0):
            node.backoff_until = 2000.0
            self.assertFalse(node.healthy)


class TestGlobalNodeHealthFunctions(unittest.TestCase):
    """Test global node health functions."""

    def setUp(self):
        """Set up test environment with proper isolation."""
        # Clear any global state before each test
        import index_core.node_health

        # Clear global variables
        index_core.node_health._shutdown_requested.clear()
        index_core.node_health._shutdown_callbacks.clear()
        index_core.node_health.node_health_tracker.clear()
        index_core.node_health.healthy_nodes.clear()

    def tearDown(self):
        """Clean up after each test."""
        # Clear any global state after each test
        import index_core.node_health

        # Clear global variables
        index_core.node_health._shutdown_requested.clear()
        index_core.node_health._shutdown_callbacks.clear()
        index_core.node_health.node_health_tracker.clear()
        index_core.node_health.healthy_nodes.clear()

    @pytest.mark.integration
    @patch(
        "index_core.node_health.config.XCP_V2_NODES",
        [{"name": "node1", "url": "http://node1.com"}, {"name": "node2", "url": "http://node2.com"}],
    )
    @patch("index_core.node_health.check_node_health")
    def test_initialize_node_health(self, mock_check_health):
        """Test initializing node health tracking."""
        from index_core.node_health import initialize_node_health, node_health_tracker

        # Mock all nodes as healthy
        mock_check_health.return_value = True

        # Clear any existing state
        node_health_tracker.clear()

        # Initialize
        result = initialize_node_health()

        # Should return True (healthy nodes found)
        self.assertTrue(result)

        # Should have created health trackers
        self.assertIn("node1", node_health_tracker)
        self.assertIn("node2", node_health_tracker)

    @patch("index_core.node_health.config.CP_BASE_DELAY", 1)
    def test_exponential_backoff(self):
        """Test exponential backoff calculation."""
        from index_core.node_health import exponential_backoff

        # Test backoff calculations
        self.assertEqual(exponential_backoff(0), 1)  # 1 * 2^0 = 1
        self.assertEqual(exponential_backoff(1), 2)  # 1 * 2^1 = 2
        self.assertEqual(exponential_backoff(2), 4)  # 1 * 2^2 = 4
        self.assertEqual(exponential_backoff(3), 8)  # 1 * 2^3 = 8

        # Test cap at 120 seconds (2 minutes)
        self.assertEqual(exponential_backoff(10), 120)  # Should cap at 120

    @pytest.mark.integration
    @patch("index_core.node_health.Backend")
    def test_node_get_stats(self, mock_backend_class):
        """Test getting node statistics."""
        # Mock the backend to prevent any network calls or blocking operations
        mock_backend = Mock()
        mock_backend_class.return_value = mock_backend

        node = NodeHealth("test-node", "http://test.com")

        # Set some values
        node.failures = 10
        node.consecutive_failures = 2
        node.total_successes = 50
        node.minor_failures = 3

        # Get stats
        stats = node.get_stats()

        # Verify stats
        self.assertEqual(stats["name"], "test-node")
        self.assertEqual(stats["url"], "http://test.com")
        self.assertEqual(stats["failures"], 10)
        self.assertEqual(stats["consecutive_failures"], 2)
        self.assertEqual(stats["total_successes"], 50)
        self.assertEqual(stats["minor_failures"], 3)
        self.assertFalse(stats["healthy"])

    @pytest.mark.integration
    @patch("index_core.node_health.Backend")
    def test_update_version(self, mock_backend_class):
        """Test updating node version information."""
        # Mock the backend to prevent any network calls or blocking operations
        mock_backend = Mock()
        mock_backend_class.return_value = mock_backend

        node = NodeHealth("test-node", "http://test.com")

        # Update version
        version_info = {"network": "mainnet", "subversion": "/Satoshi:0.21.0/"}
        node.update_version("0.21.0", version_info)

        # Verify update
        self.assertEqual(node.version, "0.21.0")
        self.assertEqual(node.version_info, version_info)


if __name__ == "__main__":
    unittest.main()
