from unittest.mock import Mock, patch

import pytest

import config
from index_core.node_health import (
    NodeHealth,
    _round_robin_index,
    get_healthy_nodes,
    get_next_healthy_node_round_robin,
    node_health_tracker,
)


class TestNodeRoundRobin:
    """Test round-robin node selection functionality."""

    def setup_method(self):
        """Setup for each test method."""
        # Reset round-robin index
        global _round_robin_index
        _round_robin_index = 0

        # Clear node health tracker
        node_health_tracker.clear()

    @patch("index_core.node_health.get_healthy_nodes")
    def test_round_robin_selection_with_multiple_nodes(self, mock_get_healthy_nodes):
        """Test that round-robin properly cycles through multiple nodes."""
        # Mock 3 healthy nodes
        mock_nodes = [
            {"name": "node1", "url": "http://node1.com:4000"},
            {"name": "node2", "url": "http://node2.com:4000"},
            {"name": "node3", "url": "http://node3.com:4000"},
        ]
        mock_get_healthy_nodes.return_value = mock_nodes

        # Test round-robin selection
        selected_nodes = []
        for i in range(6):  # Test 2 full cycles
            node = get_next_healthy_node_round_robin()
            selected_nodes.append(node["name"])

        # Should cycle through nodes in order: node1, node2, node3, node1, node2, node3
        expected = ["node1", "node2", "node3", "node1", "node2", "node3"]
        assert selected_nodes == expected

    @patch("index_core.node_health.get_healthy_nodes")
    def test_round_robin_selection_with_two_nodes(self, mock_get_healthy_nodes):
        """Test round-robin with exactly 2 nodes."""
        mock_nodes = [
            {"name": "primary", "url": "http://primary.com:4000"},
            {"name": "backup", "url": "http://backup.com:4000"},
        ]
        mock_get_healthy_nodes.return_value = mock_nodes

        # Test round-robin selection
        selected_nodes = []
        for i in range(4):
            node = get_next_healthy_node_round_robin()
            selected_nodes.append(node["name"])

        # Should alternate: primary, backup, primary, backup
        expected = ["primary", "backup", "primary", "backup"]
        assert selected_nodes == expected

    @patch("index_core.node_health.get_healthy_nodes")
    def test_round_robin_with_no_healthy_nodes(self, mock_get_healthy_nodes):
        """Test round-robin when no healthy nodes are available."""
        mock_get_healthy_nodes.return_value = []

        node = get_next_healthy_node_round_robin()
        assert node is None

    @patch("index_core.node_health.get_healthy_nodes")
    def test_round_robin_with_single_node(self, mock_get_healthy_nodes):
        """Test round-robin with only one healthy node."""
        mock_nodes = [
            {"name": "only_node", "url": "http://only.com:4000"},
        ]
        mock_get_healthy_nodes.return_value = mock_nodes

        # Should always return the same node
        for i in range(3):
            node = get_next_healthy_node_round_robin()
            assert node["name"] == "only_node"

    @patch(
        "config.XCP_V2_NODES",
        [
            {"name": "node1", "url": "http://node1.com:4000/v2"},
            {"name": "node2", "url": "http://node2.com:4000/v2"},
            {"name": "node3", "url": "http://node3.com:4000/v2"},
        ],
    )
    @patch("index_core.fetch_utils.get_healthy_nodes")
    @patch("index_core.fetch_utils.get_next_healthy_node_round_robin")
    def test_fetch_xcp_uses_round_robin_with_multiple_nodes(self, mock_round_robin, mock_get_healthy_nodes):
        """Test that fetch_xcp uses round-robin when multiple nodes are configured."""
        from index_core.fetch_utils import fetch_xcp

        # Mock round-robin to return a specific node
        mock_node = {"name": "node2", "url": "http://node2.com:4000/v2"}
        mock_round_robin.return_value = mock_node

        # Mock healthy nodes for fallback
        mock_get_healthy_nodes.return_value = [
            {"name": "node1", "url": "http://node1.com:4000/v2"},
            {"name": "node2", "url": "http://node2.com:4000/v2"},
            {"name": "node3", "url": "http://node3.com:4000/v2"},
        ]

        with patch("requests.get") as mock_requests:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.json.return_value = {"result": [], "next_cursor": None}
            mock_requests.return_value = mock_response

            # Call fetch_xcp
            result = fetch_xcp("/test")

            # Should have called round-robin selection
            mock_round_robin.assert_called_once()

            # Should have made request to the round-robin selected node
            mock_requests.assert_called_once()
            call_args = mock_requests.call_args
            assert "node2.com" in call_args[0][0]  # URL should contain node2

    @patch(
        "config.XCP_V2_NODES",
        [
            {"name": "node1", "url": "http://node1.com:4000/v2"},
            {"name": "node2", "url": "http://node2.com:4000/v2"},
        ],
    )
    @patch("index_core.fetch_utils.get_healthy_nodes")
    def test_fetch_xcp_uses_traditional_failover_with_two_nodes(self, mock_get_healthy_nodes):
        """Test that fetch_xcp uses traditional failover when only 2 nodes are configured."""
        from index_core.fetch_utils import fetch_xcp

        mock_get_healthy_nodes.return_value = [
            {"name": "node1", "url": "http://node1.com:4000/v2"},
            {"name": "node2", "url": "http://node2.com:4000/v2"},
        ]

        with patch("requests.get") as mock_requests:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.json.return_value = {"result": [], "next_cursor": None}
            mock_requests.return_value = mock_response

            with patch("index_core.fetch_utils.get_next_healthy_node_round_robin") as mock_round_robin:
                # Call fetch_xcp
                result = fetch_xcp("/test")

                # Should NOT have called round-robin with only 2 nodes
                mock_round_robin.assert_not_called()

                # Should have made request to first healthy node
                mock_requests.assert_called_once()

    def test_node_health_integration_with_round_robin(self):
        """Test that round-robin respects node health status."""
        # Create mock nodes with health trackers
        node_health_tracker["healthy_node"] = NodeHealth("healthy_node", "http://healthy.com:4000")
        node_health_tracker["unhealthy_node"] = NodeHealth("unhealthy_node", "http://unhealthy.com:4000")

        # Mark one node as unhealthy
        node_health_tracker["unhealthy_node"].mark_failure("Connection timeout")
        node_health_tracker["unhealthy_node"].mark_failure("Connection timeout")
        node_health_tracker["unhealthy_node"].mark_failure("Connection timeout")  # 3 failures

        # Mock get_healthy_nodes to only return healthy node
        with patch("index_core.node_health.get_healthy_nodes") as mock_get_healthy:
            mock_get_healthy.return_value = [
                {"name": "healthy_node", "url": "http://healthy.com:4000"},
            ]

            # Round-robin should only return the healthy node
            for i in range(3):
                node = get_next_healthy_node_round_robin()
                assert node["name"] == "healthy_node"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
