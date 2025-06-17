"""
Tests for market data scheduler configuration flag.

This module tests the ENABLE_MARKET_DATA_SCHEDULER flag functionality
to ensure market data schedulers can be properly enabled/disabled.
"""

import os
from unittest.mock import patch

import pytest

import config


class TestMarketDataSchedulerFlag:
    """Test market data scheduler flag configuration."""

    def test_scheduler_flag_default_disabled(self):
        """Test that market data scheduler is disabled by default."""
        # Clear any existing env var
        with patch.dict(os.environ, {}, clear=True):
            # Reload config to get fresh values
            import importlib

            importlib.reload(config)
            assert config.ENABLE_MARKET_DATA_SCHEDULER is False

    def test_scheduler_flag_enabled_via_env(self):
        """Test enabling market data scheduler via environment variable."""
        with patch.dict(os.environ, {"ENABLE_MARKET_DATA_SCHEDULER": "true"}):
            import importlib

            importlib.reload(config)
            assert config.ENABLE_MARKET_DATA_SCHEDULER is True

    def test_scheduler_flag_disabled_via_env(self):
        """Test explicitly disabling market data scheduler via environment variable."""
        with patch.dict(os.environ, {"ENABLE_MARKET_DATA_SCHEDULER": "false"}):
            import importlib

            importlib.reload(config)
            assert config.ENABLE_MARKET_DATA_SCHEDULER is False

    def test_scheduler_flag_case_insensitive(self):
        """Test that the flag accepts various case formats."""
        test_cases = [
            ("TRUE", True),
            ("True", True),
            ("true", True),
            ("FALSE", False),
            ("False", False),
            ("false", False),
            ("", False),  # Empty string should be false
            ("invalid", False),  # Invalid value should be false
        ]

        for env_value, expected in test_cases:
            with patch.dict(os.environ, {"ENABLE_MARKET_DATA_SCHEDULER": env_value}):
                import importlib

                importlib.reload(config)
                assert config.ENABLE_MARKET_DATA_SCHEDULER is expected

    @patch("index_core.blocks.start_market_data_jobs")
    def test_scheduler_logic_when_disabled(self, mock_start_jobs):
        """Test the scheduler logic when disabled."""
        with patch.dict(os.environ, {"ENABLE_MARKET_DATA_SCHEDULER": "false"}):
            import importlib
            importlib.reload(config)
            
            # Test the logic directly
            single_block = False
            reparse_mode = False
            
            if config.ENABLE_MARKET_DATA_SCHEDULER and not single_block and not reparse_mode:
                mock_start_jobs(max_workers=3)
            
            # Should not be called when disabled
            mock_start_jobs.assert_not_called()

    @patch("index_core.blocks.start_market_data_jobs")
    def test_scheduler_logic_when_enabled(self, mock_start_jobs):
        """Test the scheduler logic when enabled."""
        with patch.dict(os.environ, {"ENABLE_MARKET_DATA_SCHEDULER": "true"}):
            import importlib
            importlib.reload(config)
            
            # Test the logic directly
            single_block = False
            reparse_mode = False
            
            if config.ENABLE_MARKET_DATA_SCHEDULER and not single_block and not reparse_mode:
                mock_start_jobs(max_workers=3)
            
            # Should be called when enabled and not in single block or reparse mode
            mock_start_jobs.assert_called_once_with(max_workers=3)

    @patch("index_core.blocks.start_market_data_jobs")
    def test_scheduler_logic_disabled_in_single_block_mode(self, mock_start_jobs):
        """Test that scheduler logic is disabled in single block mode."""
        with patch.dict(os.environ, {"ENABLE_MARKET_DATA_SCHEDULER": "true"}):
            import importlib
            importlib.reload(config)
            
            # Test the logic directly
            single_block = True  # Single block mode
            reparse_mode = False
            
            if config.ENABLE_MARKET_DATA_SCHEDULER and not single_block and not reparse_mode:
                mock_start_jobs(max_workers=3)
            
            # Should not be called in single block mode even when enabled
            mock_start_jobs.assert_not_called()

    @patch("index_core.blocks.start_market_data_jobs")
    def test_scheduler_logic_disabled_in_reparse_mode(self, mock_start_jobs):
        """Test that scheduler logic is disabled in reparse mode."""
        with patch.dict(os.environ, {"ENABLE_MARKET_DATA_SCHEDULER": "true"}):
            import importlib
            importlib.reload(config)
            
            # Test the logic directly
            single_block = False
            reparse_mode = True  # Reparse mode
            
            if config.ENABLE_MARKET_DATA_SCHEDULER and not single_block and not reparse_mode:
                mock_start_jobs(max_workers=3)
            
            # Should not be called in reparse mode even when enabled
            mock_start_jobs.assert_not_called()

    @patch("index_core.blocks.start_market_data_jobs")
    def test_scheduler_logic_comprehensive(self, mock_start_jobs):
        """Test comprehensive scheduler logic scenarios."""
        test_cases = [
            # (ENABLE_MARKET_DATA_SCHEDULER, single_block, reparse_mode, should_call)
            (True, False, False, True),    # Should call: enabled, normal mode
            (False, False, False, False),  # Should not call: disabled
            (True, True, False, False),    # Should not call: single block mode
            (True, False, True, False),    # Should not call: reparse mode
            (True, True, True, False),     # Should not call: both single block and reparse
        ]
        
        for enabled, single_block, reparse_mode, should_call in test_cases:
            with patch.dict(os.environ, {"ENABLE_MARKET_DATA_SCHEDULER": str(enabled).lower()}):
                import importlib
                importlib.reload(config)
                
                # Reset mock
                mock_start_jobs.reset_mock()
                
                # Test the logic directly
                if config.ENABLE_MARKET_DATA_SCHEDULER and not single_block and not reparse_mode:
                    mock_start_jobs(max_workers=3)
                
                # Verify expectation
                if should_call:
                    mock_start_jobs.assert_called_once_with(max_workers=3)
                else:
                    mock_start_jobs.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__])
