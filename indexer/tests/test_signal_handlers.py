"""Tests for signal_handlers module."""

import os
import signal
import threading
import unittest
from unittest.mock import MagicMock, Mock, patch

# Import the module to avoid circular import
import index_core.signal_handlers as signal_handlers


class TestSignalHandlers(unittest.TestCase):
    """Test signal handler functionality."""

    def setUp(self):
        """Reset signal handler state before each test."""
        # Reset the call_count attribute if it exists
        if hasattr(signal_handler, "call_count"):
            delattr(signal_handler, "call_count")

    @patch('index_core.signal_handlers.logger')
    @patch('index_core.signal_handlers.server.shutdown_flag')
    @patch('index_core.signal_handlers.set_shutdown_flag')
    @patch('threading.Timer')
    def test_signal_handler_first_call(self, mock_timer, mock_set_shutdown, mock_server_flag, mock_logger):
        """Test signal handler on first interrupt."""
        # Mock timer instance
        timer_instance = Mock()
        mock_timer.return_value = timer_instance
        
        # Call signal handler
        signal_handler(signal.SIGINT, None)
        
        # Verify first call behavior
        mock_logger.info.assert_called_with("Received interrupt signal, initiating graceful shutdown...")
        mock_server_flag.set.assert_called_once()
        mock_set_shutdown.assert_called_once()
        
        # Verify timer was set up
        mock_timer.assert_called_once_with(10.0, unittest.mock.ANY)
        timer_instance.start.assert_called_once()
        self.assertTrue(timer_instance.daemon)

    @patch('index_core.signal_handlers.logger')
    @patch('os._exit')
    def test_signal_handler_second_call(self, mock_exit, mock_logger):
        """Test signal handler on second interrupt (force exit)."""
        # Simulate first call
        signal_handler.call_count = 1
        
        # Call signal handler second time
        signal_handler(signal.SIGINT, None)
        
        # Verify immediate exit
        mock_logger.warning.assert_called_with("Received second interrupt, forcing immediate exit...")
        mock_exit.assert_called_once_with(1)

    @patch('index_core.signal_handlers.logger')
    @patch('index_core.signal_handlers.server.shutdown_flag')
    @patch('index_core.signal_handlers.set_shutdown_flag')
    @patch('threading.Timer')
    def test_signal_handler_with_profiler(self, mock_timer, mock_set_shutdown, mock_server_flag, mock_logger):
        """Test signal handler with profiler instance."""
        # Mock profiler
        mock_profiler = Mock()
        
        # Set global profiler
        import index_core.signal_handlers
        index_core.signal_handlers.profiler = mock_profiler
        
        try:
            # Call signal handler
            signal_handler(signal.SIGINT, None)
            
            # Verify profiler was ended
            mock_profiler.end_block_profiling.assert_called_once()
            
        finally:
            # Clean up global
            index_core.signal_handlers.profiler = None

    @patch('index_core.signal_handlers.logger')
    @patch('index_core.signal_handlers.server.shutdown_flag')
    @patch('index_core.signal_handlers.set_shutdown_flag')
    @patch('threading.Timer')
    def test_signal_handler_profiler_exception(self, mock_timer, mock_set_shutdown, mock_server_flag, mock_logger):
        """Test signal handler when profiler raises exception."""
        # Mock profiler that raises exception
        mock_profiler = Mock()
        mock_profiler.end_block_profiling.side_effect = Exception("Profiler error")
        
        # Set global profiler
        import index_core.signal_handlers
        index_core.signal_handlers.profiler = mock_profiler
        
        try:
            # Call signal handler - should not raise
            signal_handler(signal.SIGINT, None)
            
            # Verify error was logged
            mock_logger.error.assert_called_with("Error ending profiling: Profiler error")
            
            # Verify shutdown continues
            mock_server_flag.set.assert_called_once()
            mock_set_shutdown.assert_called_once()
            
        finally:
            # Clean up global
            index_core.signal_handlers.profiler = None

    @patch('signal.signal')
    def test_setup_signal_handler_basic(self, mock_signal):
        """Test basic setup of signal handler."""
        setup_signal_handler()
        
        # Verify signal handler was registered
        mock_signal.assert_called_once_with(signal.SIGINT, signal_handler)

    @patch('signal.signal')
    def test_setup_signal_handler_with_profiler(self, mock_signal):
        """Test setup with profiler instance."""
        mock_profiler = Mock()
        
        setup_signal_handler(profiler_instance=mock_profiler)
        
        # Verify global was set
        import index_core.signal_handlers
        self.assertEqual(index_core.signal_handlers.profiler, mock_profiler)
        
        # Clean up
        index_core.signal_handlers.profiler = None

    @patch('signal.signal')
    @patch('index_core.signal_handlers.register_shutdown_callback')
    def test_setup_signal_handler_with_cp_pipeline(self, mock_register_callback, mock_signal):
        """Test setup with CP pipeline instance."""
        # Mock CP pipeline with shutdown_flag
        mock_cp_pipeline = Mock()
        mock_cp_pipeline.shutdown_flag = Mock()
        
        signal_handlers.setup_signal_handler(cp_pipeline=mock_cp_pipeline)
        
        # Verify callback was registered
        mock_register_callback.assert_called_once()
        
        # Get the registered callback
        callback = mock_register_callback.call_args[0][0]
        
        # Test the callback
        with patch('index_core.signal_handlers.logger') as mock_logger:
            callback()
            mock_logger.info.assert_called_with("CP Pipeline shutdown callback triggered")
            mock_cp_pipeline.shutdown_flag.set.assert_called_once()

    @patch('signal.signal')
    @patch('index_core.signal_handlers.register_shutdown_callback')
    @patch('index_core.signal_handlers.logger')
    def test_cp_pipeline_shutdown_callback_exception(self, mock_logger, mock_register_callback, mock_signal):
        """Test CP pipeline shutdown callback with exception."""
        # Mock CP pipeline that raises exception
        mock_cp_pipeline = Mock()
        mock_cp_pipeline.shutdown_flag.set.side_effect = Exception("Pipeline error")
        
        setup_signal_handler(cp_pipeline=mock_cp_pipeline)
        
        # Get the registered callback
        callback = mock_register_callback.call_args[0][0]
        
        # Test the callback handles exception
        callback()
        mock_logger.error.assert_called_with("Error shutting down CP pipeline: Pipeline error")

    @patch('os._exit')
    @patch('index_core.signal_handlers.logger')
    def test_force_exit_timeout(self, mock_logger, mock_exit):
        """Test force exit timeout function."""
        # Get the force_exit function from the timer
        with patch('threading.Timer') as mock_timer:
            signal_handler(signal.SIGINT, None)
            
            # Get the timeout function that was passed to Timer
            timeout_func = mock_timer.call_args[0][1]
            
            # Call the timeout function
            timeout_func()
            
            # Verify forced exit
            mock_logger.warning.assert_called_with("Shutdown timeout reached (10 seconds), forcing exit...")
            mock_exit.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()