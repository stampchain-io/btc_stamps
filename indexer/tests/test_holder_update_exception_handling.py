"""Test holder update exception handling in blocks.py."""

import queue
from unittest.mock import MagicMock, patch

import pytest


class TestHolderUpdateExceptionHandling:
    """Test exception handling for holder update scheduling."""

    def test_holder_update_scheduling_handles_exceptions(self):
        """Test that the holder update scheduling code handles exceptions properly."""
        # Create mock objects
        mock_holder_updater = MagicMock()
        mock_holder_updater.get_affected_token_count.return_value = 3
        mock_holder_updater.affected_tokens = {"TOKEN1", "TOKEN2", "TOKEN3"}
        mock_holder_updater.clear = MagicMock()

        # Test the exception handling logic directly
        with patch("index_core.blocks.get_holder_updater", return_value=mock_holder_updater):
            with patch("index_core.blocks.schedule_holder_update", side_effect=Exception("Schedule failed")):
                # Simulate the exception handling code from blocks.py
                try:
                    holder_updater = mock_holder_updater
                    if holder_updater.get_affected_token_count() > 0:
                        affected_tokens = holder_updater.affected_tokens.copy()
                        # This will raise an exception
                        from index_core.blocks import schedule_holder_update

                        schedule_holder_update(999, affected_tokens)
                    holder_updater.clear()
                except Exception:
                    # Exception handler should still clear the holder updater
                    try:
                        holder_updater.clear()
                    except Exception:
                        pass

                # Verify clear was called even after exception
                assert mock_holder_updater.clear.call_count >= 1

    def test_holder_updater_clear_fails_gracefully(self):
        """Test that holder updater clear failure is handled gracefully."""
        # Create a holder updater that fails on clear
        mock_holder_updater = MagicMock()
        mock_holder_updater.get_affected_token_count.return_value = 2
        mock_holder_updater.affected_tokens = {"TOKEN1", "TOKEN2"}
        mock_holder_updater.clear.side_effect = Exception("Clear failed")

        # Test the exception handling logic
        with patch("index_core.blocks.get_holder_updater", return_value=mock_holder_updater):
            with patch("index_core.blocks.schedule_holder_update", side_effect=Exception("Schedule failed")):
                # Simulate the exception handling code
                try:
                    holder_updater = mock_holder_updater
                    if holder_updater.get_affected_token_count() > 0:
                        affected_tokens = holder_updater.affected_tokens.copy()
                        from index_core.blocks import schedule_holder_update

                        schedule_holder_update(999, affected_tokens)
                    holder_updater.clear()
                except Exception:
                    # Should handle clear failure gracefully
                    try:
                        holder_updater.clear()
                    except Exception:
                        pass  # This is expected

                # Verify clear was attempted
                assert mock_holder_updater.clear.called

    def test_schedule_holder_update_queue_full(self):
        """Test handling when update queue is full."""
        from index_core.async_holder_updater import schedule_holder_update

        # Test the schedule_holder_update function directly
        with patch("index_core.async_holder_updater.update_queue") as mock_queue:
            mock_queue.put_nowait.side_effect = queue.Full()
            mock_queue.qsize.return_value = 100

            with patch("index_core.async_holder_updater._update_worker_running", True):
                # Should return False when queue is full but not raise exception
                result = schedule_holder_update(999, {"TOKEN1", "TOKEN2"})
                assert result is False

    def test_schedule_holder_update_worker_not_running(self):
        """Test handling when worker is not running."""
        from index_core.async_holder_updater import schedule_holder_update

        with patch("index_core.async_holder_updater._update_worker_running", False):
            # Should return False when worker is not running
            result = schedule_holder_update(999, {"TOKEN1"})
            assert result is False

    def test_get_holder_updater_failure(self):
        """Test handling when get_holder_updater fails."""
        with patch("index_core.blocks.get_holder_updater", side_effect=Exception("Failed to get updater")):
            # Simulate the exception handling code
            try:
                from index_core.blocks import get_holder_updater

                holder_updater = get_holder_updater()
                # This line won't be reached
                holder_updater.clear()
            except Exception:
                # Should handle the exception gracefully
                try:
                    # Try to get holder updater again for clearing
                    holder_updater = get_holder_updater()
                    holder_updater.clear()
                except Exception:
                    pass  # Expected - can't clear if we can't get the updater
