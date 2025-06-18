"""
Test cases for FallbackStateManager instance-specific state file functionality.

These tests validate that multiple indexer instances can run on the same machine
without conflicting state files, and that the KeyError bug in get_healthy_nodes is fixed.
"""

import hashlib
import os
import sys
import tempfile
import unittest.mock as mock
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from index_core.fallback_state import FallbackStateManager
from index_core.node_health import get_healthy_nodes


class TestFallbackStateManagerInstanceSpecific:
    """Test cases for instance-specific state file functionality."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup method run before each test."""
        # Store original environment variables
        self.original_env = {}
        db_env_vars = ["RDS_HOSTNAME", "RDS_USER", "MYSQL_USER", "RDS_DATABASE", "RDS_PORT"]
        for var in db_env_vars:
            self.original_env[var] = os.environ.get(var)

        # Clean up any existing state manager
        import index_core.fallback_state

        index_core.fallback_state._state_manager = None

    def teardown_method(self):
        """Cleanup method run after each test."""
        # Restore original environment variables
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]

        # Clean up state manager
        import index_core.fallback_state

        if index_core.fallback_state._state_manager:
            try:
                index_core.fallback_state._state_manager.cleanup_state_file()
            except:
                pass
            index_core.fallback_state._state_manager = None

    def test_default_database_config_state_file(self):
        """Test state file path with default database configuration."""
        # Clear any existing environment variables
        for var in ["RDS_HOSTNAME", "RDS_USER", "MYSQL_USER", "RDS_DATABASE", "RDS_PORT"]:
            if var in os.environ:
                del os.environ[var]

        manager = FallbackStateManager()

        # Should use default values: localhost:3306:admin:btc_stamps
        expected_db_identifier = "localhost:3306:admin:btc_stamps"
        expected_hash = hashlib.md5(expected_db_identifier.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
        expected_filename = f"btc_stamps_fallback_state_{expected_hash}.json"

        assert expected_filename in manager.state_file
        # Should be in either /tmp or project state directory
        assert "/tmp/" in manager.state_file or "state" in manager.state_file

    def test_custom_database_config_state_file(self):
        """Test state file path with custom database configuration."""
        # Set custom database configuration
        os.environ["RDS_HOSTNAME"] = "prod-db.example.com"
        os.environ["RDS_USER"] = "indexer_user"
        os.environ["RDS_DATABASE"] = "stamps_production"
        os.environ["RDS_PORT"] = "5432"

        manager = FallbackStateManager()

        # Should use custom values
        expected_db_identifier = "prod-db.example.com:5432:indexer_user:stamps_production"
        expected_hash = hashlib.md5(expected_db_identifier.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
        expected_filename = f"btc_stamps_fallback_state_{expected_hash}.json"

        assert expected_filename in manager.state_file

    def test_multiple_instances_different_state_files(self):
        """Test that different database configs produce different state files."""
        # First instance configuration
        os.environ["RDS_HOSTNAME"] = "db1.example.com"
        os.environ["RDS_DATABASE"] = "stamps_db1"
        manager1 = FallbackStateManager()

        # Second instance configuration
        os.environ["RDS_HOSTNAME"] = "db2.example.com"
        os.environ["RDS_DATABASE"] = "stamps_db2"
        manager2 = FallbackStateManager()

        # Should have different state files
        assert manager1.state_file != manager2.state_file
        assert "db1" not in manager2.state_file  # Should not contain literal db1
        assert "db2" not in manager1.state_file  # Should not contain literal db2

    def test_same_config_same_state_file(self):
        """Test that identical database configs produce the same state file."""
        # Set identical configuration
        os.environ["RDS_HOSTNAME"] = "shared-db.example.com"
        os.environ["RDS_DATABASE"] = "shared_stamps"

        manager1 = FallbackStateManager()
        manager2 = FallbackStateManager()

        # Should have the same state file
        assert manager1.state_file == manager2.state_file

    def test_fallback_to_original_on_error(self):
        """Test fallback to original behavior when hash generation fails."""
        with patch("hashlib.md5", side_effect=Exception("Hash generation failed")):
            manager = FallbackStateManager()

            # Should fall back to original filename
            assert "btc_stamps_fallback_state.json" in manager.state_file
            assert "_" not in manager.state_file.split("/")[-1].replace("btc_stamps_fallback_state.json", "")

    def test_custom_state_file_path_override(self):
        """Test that providing a custom state file path overrides the instance-specific logic."""
        custom_path = "/tmp/my_custom_state.json"
        manager = FallbackStateManager(state_file=custom_path)

        assert manager.state_file == custom_path

    def test_state_file_creation_and_cleanup(self):
        """Test that state files can be created and cleaned up without conflicts."""
        # Set up two different configurations
        os.environ["RDS_DATABASE"] = "test_db1"
        manager1 = FallbackStateManager()

        os.environ["RDS_DATABASE"] = "test_db2"
        manager2 = FallbackStateManager()

        # Start fallback mode for both
        manager1.start_fallback_mode(900000)
        manager2.start_fallback_mode(900100)

        # Both state files should exist
        assert os.path.exists(manager1.state_file)
        assert os.path.exists(manager2.state_file)
        assert manager1.state_file != manager2.state_file

        # Both should report fallback as active
        assert manager1.is_fallback_active()
        assert manager2.is_fallback_active()
        assert manager1.get_fallback_start_block() == 900000
        assert manager2.get_fallback_start_block() == 900100

        # Clean up
        manager1.cleanup_state_file()
        manager2.cleanup_state_file()

        # State files should be removed
        assert not os.path.exists(manager1.state_file)
        assert not os.path.exists(manager2.state_file)

    def test_mysql_user_fallback(self):
        """Test that MYSQL_USER is used when RDS_USER is not available."""
        # Clear all database-related environment variables first
        for var in ["RDS_HOSTNAME", "RDS_USER", "MYSQL_USER", "RDS_DATABASE", "RDS_PORT"]:
            if var in os.environ:
                del os.environ[var]

        # Set only MYSQL_USER
        os.environ["MYSQL_USER"] = "mysql_test_user"

        manager = FallbackStateManager()

        # Should use MYSQL_USER in the identifier with other defaults
        expected_db_identifier = "localhost:3306:mysql_test_user:btc_stamps"
        expected_hash = hashlib.md5(expected_db_identifier.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
        expected_filename = f"btc_stamps_fallback_state_{expected_hash}.json"

        assert expected_filename in manager.state_file


class TestNodeHealthKeyErrorFix:
    """Test cases for the KeyError bug fix in get_healthy_nodes."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup method run before each test."""
        # Clear any global state
        import index_core.node_health

        index_core.node_health.node_health_tracker.clear()
        index_core.node_health.healthy_nodes.clear()

    def teardown_method(self):
        """Cleanup method run after each test."""
        # Clear any global state
        import index_core.node_health

        index_core.node_health.node_health_tracker.clear()
        index_core.node_health.healthy_nodes.clear()

    def test_get_healthy_nodes_with_missing_name_key(self):
        """Test that get_healthy_nodes handles nodes without 'name' key gracefully."""
        import index_core.node_health

        # Simulate nodes missing the 'name' key
        index_core.node_health.healthy_nodes = [
            {"url": "http://node1.com"},  # Missing 'name'
            {"name": "node2", "url": "http://node2.com"},  # Has both
            {"name": "node3"},  # Missing 'url'
        ]

        # Should not raise KeyError
        with patch("index_core.node_health.logger") as mock_logger:
            result = get_healthy_nodes()

            # Should return the nodes without crashing
            assert len(result) == 3

            # Should have logged debug messages with 'unknown' for missing keys
            debug_calls = [call for call in mock_logger.debug.call_args_list if "Node" in str(call)]
            assert len(debug_calls) >= 3  # Should have logged all 3 nodes

    def test_get_healthy_nodes_with_missing_url_key(self):
        """Test that get_healthy_nodes handles nodes without 'url' key gracefully."""
        import index_core.node_health

        # Simulate nodes missing the 'url' key
        index_core.node_health.healthy_nodes = [
            {"name": "node_without_url"},  # Missing 'url'
            {"name": "node_with_url", "url": "http://node.com"},
        ]

        # Should not raise KeyError
        with patch("index_core.node_health.logger") as mock_logger:
            result = get_healthy_nodes()

            # Should return the nodes without crashing
            assert len(result) == 2

            # Check that debug logging handled missing URL gracefully
            debug_calls = mock_logger.debug.call_args_list
            debug_messages = [str(call) for call in debug_calls]

            # Should contain 'unknown' for the missing URL
            has_unknown_url = any("unknown" in msg for msg in debug_messages)
            assert has_unknown_url

    def test_get_healthy_nodes_with_completely_empty_nodes(self):
        """Test that get_healthy_nodes handles completely empty node dictionaries."""
        import index_core.node_health

        # Simulate empty node dictionaries
        index_core.node_health.healthy_nodes = [
            {},  # Completely empty
            {"name": "good_node", "url": "http://good.com"},
        ]

        # Should not raise KeyError
        with patch("index_core.node_health.logger") as mock_logger:
            result = get_healthy_nodes()

            # Should return the nodes without crashing
            assert len(result) == 2

            # Should have used 'unknown' for missing keys
            debug_calls = mock_logger.debug.call_args_list
            debug_messages = [str(call) for call in debug_calls]

            # Should contain 'unknown' for both missing name and URL
            has_unknown = any("unknown" in msg for msg in debug_messages)
            assert has_unknown


if __name__ == "__main__":
    pytest.main([__file__])
