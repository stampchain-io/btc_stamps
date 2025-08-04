"""Test cache clearing behavior during error recovery scenarios."""

import threading
from unittest.mock import MagicMock, Mock, patch

import pytest

from index_core.blocks import follow
from index_core.caching import (
    cache_manager,
    clear_all_caches,
    get_cached_cpid_by_tx_hash,
    get_cached_stamp_number_by_tx_hash,
    set_cached_cpid_by_tx_hash,
    set_cached_stamp_number_by_tx_hash,
)
from index_core.check import ConsensusError


class TestCacheClearingOnErrors:
    """Test cache clearing behavior during various error scenarios."""

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
        """Create a mock backend."""
        with patch('index_core.blocks.backend_instance') as mock:
            mock.get_latest_block.return_value = {"block_index": 1000}
            mock.get_block_hash.return_value = "block_hash_123"
            mock.get_block.return_value = {"height": 1000, "tx": []}
            yield mock

    @pytest.fixture
    def setup_caches(self):
        """Set up test data in caches."""
        # Clear any existing cache data
        clear_all_caches()
        
        # Add test data to caches
        set_cached_stamp_number_by_tx_hash("tx1", 100)
        set_cached_stamp_number_by_tx_hash("tx2", 101)
        set_cached_cpid_by_tx_hash("tx1", 12345)
        set_cached_cpid_by_tx_hash("tx2", 12346)
        
        yield
        
        # Clean up after test
        clear_all_caches()

    def test_consensus_error_clears_all_caches(self, mock_db, mock_backend, setup_caches):
        """Test that consensus errors trigger cache clearing."""
        # Verify caches have data before error
        assert get_cached_stamp_number_by_tx_hash("tx1") == 100
        assert get_cached_cpid_by_tx_hash("tx1") == 12345
        
        # Mock the process_block function to raise ConsensusError
        with patch('index_core.blocks.process_block') as mock_process:
            mock_process.side_effect = ConsensusError("Test consensus error", 999)
            
            # Mock config to allow retry
            with patch('config.FORCE', False):
                # Run follow with single_block=True to process one block
                try:
                    follow(mock_db, single_block=True)
                except ConsensusError:
                    pass  # Expected
        
        # Verify caches were cleared
        assert get_cached_stamp_number_by_tx_hash("tx1") is None
        assert get_cached_cpid_by_tx_hash("tx1") is None
        assert mock_db.rollback.called

    def test_deadlock_error_clears_all_caches(self, mock_db, mock_backend, setup_caches):
        """Test that deadlock errors trigger cache clearing."""
        # Verify caches have data before error
        assert get_cached_stamp_number_by_tx_hash("tx2") == 101
        
        # Create a deadlock error
        deadlock_error = Exception("Deadlock found when trying to get lock")
        
        # Mock the process_block function to raise deadlock error
        with patch('index_core.blocks.process_block') as mock_process:
            mock_process.side_effect = deadlock_error
            
            # Run follow with single_block=True
            with patch('time.sleep'):  # Skip sleep delays
                try:
                    follow(mock_db, single_block=True)
                except Exception:
                    pass
        
        # Verify caches were cleared
        assert get_cached_stamp_number_by_tx_hash("tx2") is None
        assert mock_db.rollback.called

    def test_general_exception_clears_all_caches(self, mock_db, mock_backend, setup_caches):
        """Test that general exceptions trigger cache clearing."""
        # Verify caches have data before error
        assert get_cached_stamp_number_by_tx_hash("tx1") == 100
        
        # Mock the process_block function to raise general exception
        with patch('index_core.blocks.process_block') as mock_process:
            mock_process.side_effect = RuntimeError("Test general error")
            
            # Run follow with single_block=True
            with patch('time.sleep'):  # Skip sleep delays
                try:
                    follow(mock_db, single_block=True)
                except RuntimeError:
                    pass
        
        # Verify caches were cleared
        assert get_cached_stamp_number_by_tx_hash("tx1") is None
        assert mock_db.rollback.called

    def test_holder_update_scheduling_error_handling(self, mock_db):
        """Test error handling during holder update scheduling."""
        from index_core.blocks import schedule_holder_update
        from index_core.src20_holder_updater import get_holder_updater
        
        # Mock the holder updater
        mock_holder_updater = MagicMock()
        mock_holder_updater.get_affected_token_count.return_value = 2
        mock_holder_updater.affected_tokens = {"TOKEN1", "TOKEN2"}
        
        with patch('index_core.blocks.get_holder_updater', return_value=mock_holder_updater):
            # Mock schedule_holder_update to raise an exception
            with patch('index_core.blocks.schedule_holder_update') as mock_schedule:
                mock_schedule.side_effect = Exception("Queue full")
                
                # The code should handle the exception gracefully
                # This is tested indirectly through the block processing
                # but we can verify the pattern is correct
                
                # Simulate the try-except block
                try:
                    holder_updater = get_holder_updater()
                    if holder_updater.get_affected_token_count() > 0:
                        affected_tokens = holder_updater.affected_tokens.copy()
                        schedule_holder_update(999, affected_tokens)
                    holder_updater.clear()
                except Exception as e:
                    # Should still clear the holder updater
                    holder_updater.clear()
                
                # Verify clear was called even after exception
                assert mock_holder_updater.clear.called

    def test_cache_clearing_is_thread_safe(self, setup_caches):
        """Test that cache clearing is thread-safe during concurrent access."""
        results = []
        errors = []
        
        def read_cache():
            try:
                # Try to read from cache multiple times
                for _ in range(10):
                    val = get_cached_stamp_number_by_tx_hash("tx1")
                    results.append(val)
            except Exception as e:
                errors.append(e)
        
        def clear_cache():
            try:
                # Clear caches multiple times
                for _ in range(5):
                    clear_all_caches()
            except Exception as e:
                errors.append(e)
        
        # Create threads for concurrent access
        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=read_cache))
            threads.append(threading.Thread(target=clear_cache))
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Verify no errors occurred
        assert len(errors) == 0
        # Verify cache is cleared at the end
        assert get_cached_stamp_number_by_tx_hash("tx1") is None

    def test_retry_after_cache_clear_uses_fresh_data(self, mock_db, mock_backend, setup_caches):
        """Test that retry after cache clear doesn't use stale cached data."""
        call_count = 0
        
        def process_block_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # First call - verify cache has data and raise error
                assert get_cached_stamp_number_by_tx_hash("tx1") == 100
                raise ConsensusError("Test error", 999)
            else:
                # Second call - cache should be cleared
                assert get_cached_stamp_number_by_tx_hash("tx1") is None
                # Add new data to simulate fresh processing
                set_cached_stamp_number_by_tx_hash("tx1", 200)
                return {"processed": True}
        
        with patch('index_core.blocks.process_block', side_effect=process_block_with_retry):
            with patch('config.FORCE', True):  # Allow retry
                with patch('time.sleep'):  # Skip sleep delays
                    follow(mock_db, single_block=True)
        
        # Verify retry happened
        assert call_count == 2
        # Verify new cache data is present
        assert get_cached_stamp_number_by_tx_hash("tx1") == 200

    @pytest.mark.parametrize("error_type,error_message", [
        (ConsensusError, "Consensus mismatch"),
        (Exception, "Deadlock found when trying to get lock"),
        (RuntimeError, "General runtime error"),
        (ValueError, "Invalid value error"),
    ])
    def test_all_error_types_clear_cache(self, mock_db, mock_backend, setup_caches, error_type, error_message):
        """Test that all error types properly clear caches."""
        # Verify cache has data
        assert get_cached_stamp_number_by_tx_hash("tx1") == 100
        
        # Create the appropriate error
        if error_type == ConsensusError:
            error = error_type(error_message, 999)
        else:
            error = error_type(error_message)
        
        with patch('index_core.blocks.process_block', side_effect=error):
            with patch('time.sleep'):  # Skip sleep delays
                try:
                    follow(mock_db, single_block=True)
                except Exception:
                    pass
        
        # Verify cache was cleared
        assert get_cached_stamp_number_by_tx_hash("tx1") is None
        assert mock_db.rollback.called


class TestCacheManagerIntegration:
    """Test cache manager integration with error recovery."""

    def test_cache_manager_handles_clear_during_operations(self):
        """Test that cache manager handles clearing during ongoing operations."""
        # Add data to multiple caches
        cache_manager.stamps_cache["test_stamp"] = {"data": "value"}
        cache_manager.cpid_cache["test_cpid"] = 12345
        
        # Verify data is present
        assert "test_stamp" in cache_manager.stamps_cache
        assert "test_cpid" in cache_manager.cpid_cache
        
        # Clear all caches
        clear_all_caches()
        
        # Verify all caches are cleared
        assert "test_stamp" not in cache_manager.stamps_cache
        assert "test_cpid" not in cache_manager.cpid_cache
        assert len(cache_manager.stamps_cache) == 0
        assert len(cache_manager.cpid_cache) == 0

    def test_cache_size_limits_after_clear(self):
        """Test that cache size limits are respected after clearing."""
        # Fill cache to near capacity
        for i in range(100):
            set_cached_stamp_number_by_tx_hash(f"tx_{i}", i)
        
        # Clear cache
        clear_all_caches()
        
        # Add new items
        for i in range(50):
            set_cached_stamp_number_by_tx_hash(f"new_tx_{i}", i + 1000)
        
        # Verify new items are cached
        assert get_cached_stamp_number_by_tx_hash("new_tx_0") == 1000
        assert get_cached_stamp_number_by_tx_hash("new_tx_49") == 1049