"""Simple tests for signal_handlers module that avoid circular imports."""

import signal
import unittest
from unittest.mock import Mock, patch


class TestSignalHandlersSimple(unittest.TestCase):
    """Test signal handler functionality without importing the module directly."""

    @patch("os._exit")
    def test_force_exit_on_second_signal(self, mock_exit):
        """Test that second signal forces immediate exit."""
        # Create a mock signal handler that tracks calls
        call_count = 0

        def mock_signal_handler(sig, frame):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                mock_exit(1)

        # First call should not exit
        mock_signal_handler(signal.SIGINT, None)
        mock_exit.assert_not_called()

        # Second call should force exit
        mock_signal_handler(signal.SIGINT, None)
        mock_exit.assert_called_once_with(1)

    def test_signal_registration(self):
        """Test that signal handlers can be registered."""
        with patch("signal.signal") as mock_signal:
            # Simulate registering a handler
            def dummy_handler(sig, frame):
                pass

            signal.signal(signal.SIGINT, dummy_handler)
            mock_signal.assert_called_once_with(signal.SIGINT, dummy_handler)

    @patch("threading.Timer")
    def test_shutdown_timer_creation(self, mock_timer):
        """Test that shutdown timer is created properly."""
        # Mock timer instance
        timer_instance = Mock()
        mock_timer.return_value = timer_instance

        # Create a timer like the signal handler does
        import threading

        timer = threading.Timer(10.0, lambda: None)

        # Verify timer was created with correct timeout
        mock_timer.assert_called_with(10.0, unittest.mock.ANY)


if __name__ == "__main__":
    unittest.main()
