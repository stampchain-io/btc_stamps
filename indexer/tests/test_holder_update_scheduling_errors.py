"""Test holder update scheduling error handling."""

import queue
from unittest.mock import MagicMock, Mock, patch

import pytest

from index_core.async_holder_updater import HolderUpdateTask, schedule_holder_update
from index_core.blocks import follow
from index_core.src20_holder_updater import get_holder_updater


class TestHolderUpdateSchedulingErrors:
    """Test error handling for holder update scheduling."""

    @pytest.fixture
    def mock_holder_updater(self):
        """Create a mock holder updater."""
        updater = MagicMock()
        updater.get_affected_token_count.return_value = 3
        updater.affected_tokens = {"TOKEN1", "TOKEN2", "TOKEN3"}
        updater.clear = MagicMock()
        return updater

    @pytest.fixture
    def mock_db(self):
        """Create a mock database connection."""
        db = MagicMock()
        db.rollback = MagicMock()
        db.commit = MagicMock()
        db.begin = MagicMock()
        db.cursor = MagicMock()
        return db

    @pytest.fixture
    def mock_backend(self):
        """Create a mock backend for block processing."""
        with patch('index_core.blocks.backend_instance') as mock:
            mock.get_latest_block.return_value = {"block_index": 1000}
            mock.get_block_hash.return_value = "block_hash_123"
            mock.get_block.return_value = {"height": 1000, "tx": []}
            yield mock

    def test_schedule_holder_update_queue_full(self):
        """Test handling when update queue is full."""
        # Test the schedule_holder_update function directly
        with patch('index_core.async_holder_updater.update_queue') as mock_queue:
            mock_queue.put_nowait.side_effect = queue.Full()
            mock_queue.qsize.return_value = 100
            
            # Should return False when queue is full
            result = schedule_holder_update(999, {"TOKEN1", "TOKEN2"})
            assert result is False

    def test_schedule_holder_update_worker_not_running(self):
        """Test handling when worker is not running."""
        with patch('index_core.async_holder_updater._update_worker_running', False):
            # Should return False when worker is not running
            result = schedule_holder_update(999, {"TOKEN1"})
            assert result is False

    def test_holder_update_scheduling_exception_in_block_processing(self, mock_db, mock_backend, mock_holder_updater):
        """Test that holder update scheduling exceptions don't crash block processing."""
        # Mock the necessary components
        with patch('index_core.blocks.get_holder_updater', return_value=mock_holder_updater):
            with patch('index_core.blocks.schedule_holder_update') as mock_schedule:
                # Make schedule_holder_update raise an exception
                mock_schedule.side_effect = RuntimeError("Test scheduling error")
                
                # Mock process_block to return success
                with patch('index_core.blocks.process_block') as mock_process:
                    mock_process.return_value = {
                        "processed": True,
                        "src20_in_block": ["TOKEN1"],
                        "block_index": 1000
                    }
                    
                    # Mock other necessary functions
                    with patch('index_core.blocks.commit_and_update_block', return_value=1001):
                        with patch('index_core.blocks.should_update_market_data', True):
                            # Run block processing
                            follow(mock_db, single_block=True)
                
                # Verify holder updater was cleared despite the exception
                assert mock_holder_updater.clear.called
                # Verify block processing continued (commit was called)
                assert mock_db.commit.called

    def test_holder_updater_clear_fails_after_scheduling_error(self, mock_db, mock_backend):
        """Test handling when both scheduling and clearing fail."""
        # Create a holder updater that fails on clear
        failing_updater = MagicMock()
        failing_updater.get_affected_token_count.return_value = 2
        failing_updater.affected_tokens = {"TOKEN1", "TOKEN2"}
        failing_updater.clear.side_effect = Exception("Clear failed")
        
        with patch('index_core.blocks.get_holder_updater', return_value=failing_updater):
            with patch('index_core.blocks.schedule_holder_update') as mock_schedule:
                # Make schedule_holder_update raise an exception
                mock_schedule.side_effect = Exception("Scheduling failed")
                
                # Mock process_block to return success
                with patch('index_core.blocks.process_block') as mock_process:
                    mock_process.return_value = {
                        "processed": True,
                        "src20_in_block": ["TOKEN1"],
                        "block_index": 1000
                    }
                    
                    with patch('index_core.blocks.commit_and_update_block', return_value=1001):
                        with patch('index_core.blocks.should_update_market_data', True):
                            # Run block processing - should not crash
                            follow(mock_db, single_block=True)
                
                # Verify clear was attempted
                assert failing_updater.clear.called
                # Verify block processing continued despite both failures
                assert mock_db.commit.called

    def test_holder_updater_with_no_affected_tokens(self, mock_db, mock_backend):
        """Test that scheduling is skipped when no tokens are affected."""
        # Create a holder updater with no affected tokens
        empty_updater = MagicMock()
        empty_updater.get_affected_token_count.return_value = 0
        empty_updater.affected_tokens = set()
        empty_updater.clear = MagicMock()
        
        with patch('index_core.blocks.get_holder_updater', return_value=empty_updater):
            with patch('index_core.blocks.schedule_holder_update') as mock_schedule:
                # Mock process_block to return success
                with patch('index_core.blocks.process_block') as mock_process:
                    mock_process.return_value = {
                        "processed": True,
                        "src20_in_block": [],
                        "block_index": 1000
                    }
                    
                    with patch('index_core.blocks.commit_and_update_block', return_value=1001):
                        with patch('index_core.blocks.should_update_market_data', True):
                            # Run block processing
                            follow(mock_db, single_block=True)
                
                # Verify schedule_holder_update was not called (no tokens to update)
                assert not mock_schedule.called
                # Verify clear was still called
                assert empty_updater.clear.called

    @pytest.mark.parametrize("exception_type,exception_msg", [
        (queue.Full, "Queue is full"),
        (RuntimeError, "Worker thread died"),
        (ValueError, "Invalid block index"),
        (AttributeError, "Missing affected_tokens attribute"),
    ])
    def test_various_scheduling_exceptions(self, mock_db, mock_backend, mock_holder_updater, exception_type, exception_msg):
        """Test handling of various exception types during scheduling."""
        with patch('index_core.blocks.get_holder_updater', return_value=mock_holder_updater):
            with patch('index_core.blocks.schedule_holder_update') as mock_schedule:
                # Make schedule_holder_update raise the specified exception
                mock_schedule.side_effect = exception_type(exception_msg)
                
                # Mock process_block to return success
                with patch('index_core.blocks.process_block') as mock_process:
                    mock_process.return_value = {
                        "processed": True,
                        "src20_in_block": ["TOKEN1"],
                        "block_index": 1000
                    }
                    
                    with patch('index_core.blocks.commit_and_update_block', return_value=1001):
                        with patch('index_core.blocks.should_update_market_data', True):
                            # Run block processing - should handle exception gracefully
                            follow(mock_db, single_block=True)
                
                # Verify holder updater was cleared despite the exception
                assert mock_holder_updater.clear.called
                # Verify block processing continued
                assert mock_db.commit.called

    def test_holder_updater_get_fails(self, mock_db, mock_backend):
        """Test handling when get_holder_updater itself fails."""
        with patch('index_core.blocks.get_holder_updater') as mock_get:
            # Make get_holder_updater raise an exception
            mock_get.side_effect = Exception("Failed to get holder updater")
            
            # Mock process_block to return success
            with patch('index_core.blocks.process_block') as mock_process:
                mock_process.return_value = {
                    "processed": True,
                    "src20_in_block": ["TOKEN1"],
                    "block_index": 1000
                }
                
                with patch('index_core.blocks.commit_and_update_block', return_value=1001):
                    with patch('index_core.blocks.should_update_market_data', True):
                        # Run block processing - should handle exception gracefully
                        follow(mock_db, single_block=True)
            
            # Verify block processing continued despite holder updater failure
            assert mock_db.commit.called


class TestHolderUpdateIntegration:
    """Integration tests for holder update scheduling with real components."""

    def test_holder_update_task_creation(self):
        """Test that HolderUpdateTask is created correctly."""
        task = HolderUpdateTask(
            block_index=1000,
            affected_tokens={"TOKEN1", "TOKEN2"},
            force=False
        )
        
        assert task.block_index == 1000
        assert task.affected_tokens == {"TOKEN1", "TOKEN2"}
        assert task.force is False

    def test_schedule_with_empty_token_set(self):
        """Test scheduling with empty token set."""
        with patch('index_core.async_holder_updater._update_worker_running', True):
            # Should return True but not queue anything
            result = schedule_holder_update(1000, set(), force=False)
            assert result is True

    def test_schedule_with_force_flag(self):
        """Test scheduling with force flag."""
        with patch('index_core.async_holder_updater._update_worker_running', True):
            with patch('index_core.async_holder_updater.update_queue') as mock_queue:
                mock_queue.qsize.return_value = 5
                
                # Schedule with force flag
                result = schedule_holder_update(1000, set(), force=True)
                
                # Should queue the task even with empty token set
                assert result is True
                mock_queue.put_nowait.assert_called_once()
                
                # Verify the task has force=True
                call_args = mock_queue.put_nowait.call_args[0][0]
                assert isinstance(call_args, HolderUpdateTask)
                assert call_args.force is True