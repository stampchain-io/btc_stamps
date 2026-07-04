"""Tests for critical failure handler functionality."""

import logging
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from index_core.critical_failure_handler import (
    CriticalFailureHandler,
    CriticalFailureType,
    emergency_db_rollback,
    handle_critical_failure,
    register_cleanup_callback,
    set_db_connection,
)


class TestCriticalFailureHandler:
    """Test the critical failure handler functionality."""

    def test_handler_initialization(self):
        """Test that handler initializes correctly."""
        handler = CriticalFailureHandler()
        assert handler._cleanup_callbacks == []
        assert handler._shutdown_timeout == 30
        assert hasattr(handler._lock, "acquire") and hasattr(handler._lock, "release")

    def test_register_cleanup_callback(self):
        """Test registering cleanup callbacks."""
        handler = CriticalFailureHandler()

        def dummy_callback():
            pass

        handler.register_cleanup_callback(dummy_callback)
        assert dummy_callback in handler._cleanup_callbacks

        # Test duplicate registration doesn't add twice
        handler.register_cleanup_callback(dummy_callback)
        assert handler._cleanup_callbacks.count(dummy_callback) == 1

    def test_unregister_cleanup_callback(self):
        """Test unregistering cleanup callbacks."""
        handler = CriticalFailureHandler()

        def dummy_callback():
            pass

        handler.register_cleanup_callback(dummy_callback)
        handler.unregister_cleanup_callback(dummy_callback)
        assert dummy_callback not in handler._cleanup_callbacks

    @patch("index_core.critical_failure_handler.sys.exit")
    @patch("index_core.critical_failure_handler.logger")
    def test_handle_critical_failure_basic(self, mock_logger, mock_sys_exit):
        """Test basic critical failure handling."""
        handler = CriticalFailureHandler()

        handler.handle_critical_failure(
            failure_type=CriticalFailureType.DATABASE_CORRUPTION, error_message="Test error", exit_code=2
        )

        # Verify logging occurred
        mock_logger.critical.assert_called()

        # Verify sys.exit was called with correct code
        mock_sys_exit.assert_called_once_with(2)

    @patch("index_core.critical_failure_handler.sys.exit")
    def test_cleanup_callbacks_executed(self, mock_sys_exit):
        """Test that cleanup callbacks are executed."""
        handler = CriticalFailureHandler()

        callback_executed = []

        def test_callback():
            callback_executed.append(True)

        handler.register_cleanup_callback(test_callback)

        handler.handle_critical_failure(
            failure_type=CriticalFailureType.CONSENSUS_MISMATCH, error_message="Test consensus error", block_index=12345
        )

        # Verify callback was executed
        assert len(callback_executed) == 1

    @patch("index_core.critical_failure_handler.sys.exit")
    def test_cleanup_timeout_protection(self, mock_sys_exit):
        """Test that cleanup operations respect timeout."""
        handler = CriticalFailureHandler()
        handler._shutdown_timeout = 0.1  # Very short timeout for testing

        def slow_callback():
            time.sleep(0.2)  # Longer than timeout

        handler.register_cleanup_callback(slow_callback)

        start_time = time.time()
        handler.handle_critical_failure(failure_type=CriticalFailureType.DATABASE_CORRUPTION, error_message="Test timeout")
        duration = time.time() - start_time

        # Should not take much longer than timeout
        assert duration < 0.5

    def test_emergency_db_rollback_with_connection(self):
        """Test emergency database rollback when connection exists."""
        mock_db = MagicMock()
        set_db_connection(mock_db)

        emergency_db_rollback()

        mock_db.rollback.assert_called_once()

    def test_emergency_db_rollback_without_connection(self):
        """Test emergency database rollback when no connection exists."""
        set_db_connection(None)

        # Should not raise exception
        emergency_db_rollback()

    def test_emergency_db_rollback_with_exception(self):
        """Test emergency database rollback handles exceptions gracefully."""
        mock_db = MagicMock()
        mock_db.rollback.side_effect = Exception("Rollback failed")
        set_db_connection(mock_db)

        # Should not raise exception
        emergency_db_rollback()
        mock_db.rollback.assert_called_once()

    @patch("index_core.critical_failure_handler.sys.exit")
    def test_convenience_function(self, mock_sys_exit):
        """Test the convenience handle_critical_failure function."""
        handle_critical_failure(
            failure_type=CriticalFailureType.ROLLBACK_LOOP, error_message="Test rollback loop", block_index=67890, exit_code=4
        )

        mock_sys_exit.assert_called_once_with(4)

    def test_global_callback_registration(self):
        """Test global callback registration functions."""

        def test_callback():
            pass

        # Test registration
        register_cleanup_callback(test_callback)

        from index_core.critical_failure_handler import critical_failure_handler

        assert test_callback in critical_failure_handler._cleanup_callbacks

    @patch("index_core.critical_failure_handler.sys.exit")
    def test_failure_type_enum_values(self, mock_sys_exit):
        """Test that all failure types are properly handled."""
        handler = CriticalFailureHandler()

        failure_types = [
            CriticalFailureType.CONSENSUS_MISMATCH,
            CriticalFailureType.DATABASE_CORRUPTION,
            CriticalFailureType.ROLLBACK_LOOP,
            CriticalFailureType.BLOCKCHAIN_REORG_FAILURE,
            CriticalFailureType.INITIALIZATION_FAILURE,
        ]

        for failure_type in failure_types:
            handler.handle_critical_failure(failure_type=failure_type, error_message=f"Test {failure_type.value}", exit_code=1)

        # Verify sys.exit was called for each failure type
        assert mock_sys_exit.call_count == len(failure_types)
