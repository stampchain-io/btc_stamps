"""Test consensus error handling with FORCE mode and retry logic."""

import os
from unittest import mock

import pytest

import config
from index_core.check import ConsensusError, consensus_hash


class TestConsensusErrorHandling:
    """Test suite for consensus error handling functionality."""

    def test_consensus_error_raised_without_force(self):
        """Test that ConsensusError is raised when FORCE is not set."""
        # Save original FORCE value
        original_force = config.FORCE
        
        try:
            # Ensure FORCE is False
            config.FORCE = False
            
            # Create mock database
            mock_db = mock.MagicMock()
            cursor = mock.MagicMock()
            cursor.fetchall.return_value = []
            cursor.fetchone.return_value = None
            mock_db.cursor.return_value = cursor
            
            # This should raise ConsensusError for block 830000 (in checkpoints)
            with pytest.raises(ConsensusError) as exc_info:
                consensus_hash(
                    mock_db,
                    block_index=830000,
                    field="txlist_hash",
                    previous_consensus_hash=None,
                    content="test_content"
                )
            
            # The error could be either about empty previous hash or incorrect consensus hash
            error_msg = str(exc_info.value)
            assert "block 830000" in error_msg
            assert ("Empty previous" in error_msg or "Incorrect txlist_hash" in error_msg)
            
        finally:
            # Restore original FORCE value
            config.FORCE = original_force

    def test_consensus_error_not_raised_with_force(self):
        """Test that ConsensusError is not raised when FORCE is True."""
        # Save original FORCE value
        original_force = config.FORCE
        
        try:
            # Set FORCE to True
            config.FORCE = True
            
            # Create mock database
            mock_db = mock.MagicMock()
            cursor = mock.MagicMock()
            cursor.fetchall.return_value = []
            cursor.fetchone.return_value = None
            mock_db.cursor.return_value = cursor
            
            # This should NOT raise ConsensusError even for mismatched checkpoint
            result = consensus_hash(
                mock_db,
                block_index=830000,
                field="txlist_hash",
                previous_consensus_hash=None,
                content="test_content"
            )
            
            # Should return calculated hash and None for found_hash
            assert result[0] is not None  # calculated_hash
            assert result[1] is None  # found_hash
            
        finally:
            # Restore original FORCE value
            config.FORCE = original_force

    def test_max_consensus_retries_environment_variable(self):
        """Test that MAX_CONSENSUS_RETRIES can be set via environment variable."""
        # Save original value
        original_value = os.environ.get("MAX_CONSENSUS_RETRIES")
        
        try:
            # Test default value
            if "MAX_CONSENSUS_RETRIES" in os.environ:
                del os.environ["MAX_CONSENSUS_RETRIES"]
            # Need to reload config to pick up the change
            import importlib
            importlib.reload(config)
            assert config.MAX_CONSENSUS_RETRIES == 3
            
            # Test custom value
            os.environ["MAX_CONSENSUS_RETRIES"] = "5"
            importlib.reload(config)
            assert config.MAX_CONSENSUS_RETRIES == 5
            
        finally:
            # Restore original value
            if original_value is not None:
                os.environ["MAX_CONSENSUS_RETRIES"] = original_value
            elif "MAX_CONSENSUS_RETRIES" in os.environ:
                del os.environ["MAX_CONSENSUS_RETRIES"]
            # Reload config to restore original state
            import importlib
            importlib.reload(config)

    def test_force_mode_environment_variable(self):
        """Test that FORCE can be set via environment variable."""
        # Save original value
        original_value = os.environ.get("FORCE")
        
        try:
            # Test False value (default)
            os.environ["FORCE"] = "false"
            import importlib
            importlib.reload(config)
            assert config.FORCE is False
            
            # Test True value
            os.environ["FORCE"] = "true"
            importlib.reload(config)
            assert config.FORCE is True
            
            # Test case insensitive
            os.environ["FORCE"] = "TRUE"
            importlib.reload(config)
            assert config.FORCE is True
            
        finally:
            # Restore original value
            if original_value is not None:
                os.environ["FORCE"] = original_value
            elif "FORCE" in os.environ:
                del os.environ["FORCE"]
            # Reload config to restore original state
            import importlib
            importlib.reload(config)

    def test_server_initialize_preserves_force_from_env(self):
        """Test that server.initialize_config doesn't override FORCE from environment."""
        from index_core.server import initialize_config
        
        # Save original values
        original_force_env = os.environ.get("FORCE")
        original_force_config = config.FORCE
        
        try:
            # Set FORCE in environment
            os.environ["FORCE"] = "true"
            # Reload config to pick up env change
            import importlib
            importlib.reload(config)
            
            # Call initialize_config without force parameter
            initialize_config()
            
            # FORCE should still be True from environment
            assert config.FORCE is True
            
            # Call initialize_config with force=False (should not override env)
            initialize_config(force=None)
            assert config.FORCE is True
            
            # Call initialize_config with explicit force=True
            initialize_config(force=True)
            assert config.FORCE is True
            
            # Call initialize_config with explicit force=False (should override)
            initialize_config(force=False)
            assert config.FORCE is False
            
        finally:
            # Restore original values
            if original_force_env is not None:
                os.environ["FORCE"] = original_force_env
            elif "FORCE" in os.environ:
                del os.environ["FORCE"]
            config.FORCE = original_force_config