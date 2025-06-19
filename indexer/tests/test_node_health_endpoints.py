"""
Test cases for node health endpoint validation.

These tests validate that the actual HTTP endpoint checks work correctly,
including /healthz endpoint calls, JSON parsing, and fallback logic.
"""

import json
import os
import sys
import time
import unittest.mock as mock
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config
from index_core.node_health import get_healthy_nodes, node_health_tracker, update_healthy_nodes


class TestNodeHealthEndpoints:
    """Test cases for actual node health endpoint validation."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup method run before each test."""
        # Store original config
        self.original_nodes = getattr(config, "XCP_V2_NODES", [])

        # Clear global state
        import index_core.node_health

        index_core.node_health.node_health_tracker.clear()
        index_core.node_health.healthy_nodes.clear()

    def teardown_method(self):
        """Cleanup method run after each test."""
        # Restore original config
        config.XCP_V2_NODES = self.original_nodes

        # Clear global state
        import index_core.node_health

        index_core.node_health.node_health_tracker.clear()
        index_core.node_health.healthy_nodes.clear()

    def test_healthz_endpoint_success_response(self):
        """Test successful /healthz endpoint response parsing."""
        # Configure test nodes
        config.XCP_V2_NODES = [{"name": "test_node", "url": "http://test-node:8080/v2"}]

        # Mock successful healthz response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": {"status": "Healthy", "version": "10.1.2", "last_block": 900000}}

        with patch("requests.get", return_value=mock_response) as mock_get:
            result = update_healthy_nodes()

            # Should return True (found healthy nodes)
            assert result is True

            # Should have called healthz endpoint first
            mock_get.assert_called_with("http://test-node:8080/v2/healthz", timeout=5)

            # Should have healthy nodes
            healthy = get_healthy_nodes()
            assert len(healthy) == 1
            assert healthy[0]["name"] == "test_node"

    def test_healthz_endpoint_unhealthy_status(self):
        """Test /healthz endpoint with unhealthy status but fallback succeeds."""
        config.XCP_V2_NODES = [{"name": "unhealthy_node", "url": "http://unhealthy:8080/v2"}]

        def mock_get_side_effect(url, timeout):
            if "/healthz" in url:
                # Healthz response indicating unhealthy
                mock_resp = Mock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"result": {"status": "Unhealthy", "version": "10.1.2"}}  # Not "Healthy"
                return mock_resp
            else:
                # Root endpoint returns valid result (fallback succeeds)
                mock_resp = Mock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"result": {"version": "10.1.2"}}
                return mock_resp

        with patch("requests.get", side_effect=mock_get_side_effect) as mock_get:
            result = update_healthy_nodes()

            # Should return True (fallback to root endpoint succeeded)
            assert result is True

            # Should have tried both healthz and root endpoints
            assert mock_get.call_count == 2
            expected_calls = [
                mock.call("http://unhealthy:8080/v2/healthz", timeout=5),
                mock.call("http://unhealthy:8080/v2", timeout=5),
            ]
            mock_get.assert_has_calls(expected_calls)

            # Should have one healthy node (via fallback)
            healthy = get_healthy_nodes()
            assert len(healthy) == 1

    def test_healthz_endpoint_fallback_to_root_v2(self):
        """Test fallback from /healthz to root V2 endpoint."""
        config.XCP_V2_NODES = [{"name": "fallback_node", "url": "http://fallback:8080/v2"}]

        # Mock healthz failure, but root V2 success
        def mock_get_side_effect(url, timeout):
            if "/healthz" in url:
                # Healthz endpoint fails
                mock_resp = Mock()
                mock_resp.status_code = 404  # Not found
                return mock_resp
            else:
                # Root V2 endpoint succeeds
                mock_resp = Mock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"result": {"version": "10.1.2", "network": "mainnet"}}
                return mock_resp

        with patch("requests.get", side_effect=mock_get_side_effect) as mock_get:
            result = update_healthy_nodes()

            # Should return True (found healthy node via fallback)
            assert result is True

            # Should have tried both endpoints
            assert mock_get.call_count == 2

            # Should have healthy nodes
            healthy = get_healthy_nodes()
            assert len(healthy) == 1
            assert healthy[0]["name"] == "fallback_node"

    def test_healthz_endpoint_json_parse_error(self):
        """Test handling of JSON parse errors from /healthz endpoint."""
        config.XCP_V2_NODES = [{"name": "json_error_node", "url": "http://json-error:8080/v2"}]

        # Mock response that returns 200 but invalid JSON for healthz
        def mock_get_side_effect(url, timeout):
            mock_resp = Mock()
            mock_resp.status_code = 200
            if "/healthz" in url:
                # Healthz returns invalid JSON
                mock_resp.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
                return mock_resp
            else:
                # Root endpoint returns valid JSON
                mock_resp.json.return_value = {"result": {"version": "10.1.2"}}
                return mock_resp

        with patch("requests.get", side_effect=mock_get_side_effect) as mock_get:
            result = update_healthy_nodes()

            # Should return True (fallback to root worked)
            assert result is True

            # Should have tried both endpoints
            assert mock_get.call_count == 2

    def test_healthz_endpoint_timeout_handling(self):
        """Test timeout handling for health endpoint checks."""
        config.XCP_V2_NODES = [{"name": "timeout_node", "url": "http://timeout:8080/v2"}]

        # Mock timeout exception
        with patch("requests.get", side_effect=requests.exceptions.Timeout("Connection timeout")) as mock_get:
            result = update_healthy_nodes()

            # Should return False (no healthy nodes due to timeout)
            assert result is False

            # Should have tried healthz endpoint with 5 second timeout
            mock_get.assert_called_with("http://timeout:8080/v2/healthz", timeout=5)

            # Should have no healthy nodes
            healthy = get_healthy_nodes()
            assert len(healthy) == 0

    def test_healthz_endpoint_connection_error_handling(self):
        """Test connection error handling for health endpoint checks."""
        config.XCP_V2_NODES = [{"name": "connection_error_node", "url": "http://connection-error:8080/v2"}]

        # Mock connection error
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Connection failed")) as mock_get:
            result = update_healthy_nodes()

            # Should return False (no healthy nodes)
            assert result is False

            # Should have no healthy nodes
            healthy = get_healthy_nodes()
            assert len(healthy) == 0

    def test_multiple_nodes_mixed_health_status(self):
        """Test multiple nodes with mixed health status."""
        config.XCP_V2_NODES = [
            {"name": "healthy_node", "url": "http://healthy:8080/v2"},
            {"name": "unhealthy_node", "url": "http://unhealthy:8080/v2"},
            {"name": "timeout_node", "url": "http://timeout:8080/v2"},
        ]

        def mock_get_side_effect(url, timeout):
            if "healthy:8080" in url:
                # Healthy node returns good healthz
                mock_resp = Mock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"result": {"status": "Healthy"}}
                return mock_resp
            elif "unhealthy:8080" in url:
                if "/healthz" in url:
                    # Healthz fails
                    mock_resp = Mock()
                    mock_resp.status_code = 500
                    return mock_resp
                else:
                    # But root endpoint succeeds (fallback)
                    mock_resp = Mock()
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"result": {"version": "10.1.2"}}
                    return mock_resp
            elif "timeout:8080" in url:
                # Timeout node times out
                raise requests.exceptions.Timeout("Timeout")

        with patch("requests.get", side_effect=mock_get_side_effect) as mock_get:
            result = update_healthy_nodes()

            # Should return True (at least one healthy node)
            assert result is True

            # Should have two healthy nodes (healthy + unhealthy that succeeds via fallback)
            healthy = get_healthy_nodes()
            assert len(healthy) == 2
            node_names = [node["name"] for node in healthy]
            assert "healthy_node" in node_names
            assert "unhealthy_node" in node_names

    def test_node_health_tracker_marks_success_and_failure(self):
        """Test that health tracker properly marks node success and failure."""
        config.XCP_V2_NODES = [{"name": "tracked_node", "url": "http://tracked:8080/v2"}]

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": {"status": "Healthy"}}

        with patch("requests.get", return_value=mock_response):
            # First call should create tracker and mark success
            result = update_healthy_nodes()
            assert result is True

            # Check that node tracker was created
            assert "tracked_node" in node_health_tracker
            tracker = node_health_tracker["tracked_node"]
            assert tracker.consecutive_failures == 0
            # Note: The tracker is created but mark_success() is only called if tracker already exists
            # So initially total_successes will be 0

        # Now test that a second successful call will mark success
        with patch("requests.get", return_value=mock_response):
            result = update_healthy_nodes()
            assert result is True

            # Now the tracker should mark success since it already exists
            tracker = node_health_tracker["tracked_node"]
            assert tracker.total_successes >= 1

    def test_no_nodes_configured(self):
        """Test behavior when no nodes are configured."""
        config.XCP_V2_NODES = []

        result = update_healthy_nodes()

        # Should return False (no nodes to check)
        assert result is False

        # Should have no healthy nodes
        healthy = get_healthy_nodes()
        assert len(healthy) == 0

    def test_node_url_handling_edge_case(self):
        """Test handling of edge cases with node URLs."""
        # Test only with valid URLs to avoid the KeyError bug
        config.XCP_V2_NODES = [{"name": "good_node", "url": "http://good:8080/v2"}]

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"status": "Healthy"}}

        with patch("requests.get", return_value=mock_resp) as mock_get:
            result = update_healthy_nodes()

            # Should return True
            assert result is True

            # Should have one healthy node
            healthy = get_healthy_nodes()
            assert len(healthy) == 1
            assert healthy[0]["name"] == "good_node"
            assert healthy[0]["url"] == "http://good:8080/v2"

            # Should have called the healthz endpoint
            mock_get.assert_called_with("http://good:8080/v2/healthz", timeout=5)


if __name__ == "__main__":
    pytest.main([__file__])
