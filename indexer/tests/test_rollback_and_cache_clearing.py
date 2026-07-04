"""Test rollback and cache clearing functionality."""

from unittest.mock import MagicMock, patch

import pytest

from index_core.blocks import rollback_and_clear_caches
from index_core.caching import cache_manager, clear_all_caches


class TestRollbackAndCacheClearing:
    """Test the rollback_and_clear_caches helper function."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database connection."""
        db = MagicMock()
        db.rollback = MagicMock()
        return db

    @pytest.fixture
    def setup_test_cache_data(self):
        """Set up test data in caches."""
        # Clear any existing cache data
        clear_all_caches()

        # Add test data to caches using cache_manager
        cache_manager.set_cache_value("stamp", "test_tx1", {"stamp_number": 100})
        cache_manager.set_cache_value("stamp", "test_tx2", {"stamp_number": 101})
        cache_manager.set_cache_value("block", "test_tx1", 12345)
        cache_manager.set_cache_value("block", "test_tx2", 12346)

        yield

        # Clean up after test
        clear_all_caches()

    def test_rollback_and_clear_caches_consensus_error(self, mock_db, setup_test_cache_data):
        """Test rollback_and_clear_caches for consensus error."""
        # Verify caches have data before
        assert cache_manager.get_cache_value("stamp", "test_tx1") is not None
        assert cache_manager.get_cache_value("block", "test_tx1") is not None

        # Call the function
        rollback_and_clear_caches(mock_db, "consensus")

        # Verify rollback was called
        mock_db.rollback.assert_called_once()

        # Verify caches were cleared
        assert cache_manager.get_cache_value("stamp", "test_tx1") is None
        assert cache_manager.get_cache_value("block", "test_tx1") is None

    def test_rollback_and_clear_caches_deadlock_error(self, mock_db, setup_test_cache_data):
        """Test rollback_and_clear_caches for deadlock error."""
        # Verify caches have data before
        assert cache_manager.get_cache_value("stamp", "test_tx2") is not None
        assert cache_manager.get_cache_value("block", "test_tx2") is not None

        # Call the function
        rollback_and_clear_caches(mock_db, "deadlock")

        # Verify rollback was called
        mock_db.rollback.assert_called_once()

        # Verify caches were cleared
        assert cache_manager.get_cache_value("stamp", "test_tx2") is None
        assert cache_manager.get_cache_value("block", "test_tx2") is None

    def test_rollback_and_clear_caches_general_error(self, mock_db, setup_test_cache_data):
        """Test rollback_and_clear_caches for general error."""
        # Verify caches have data before
        assert cache_manager.get_cache_value("stamp", "test_tx1") is not None

        # Call the function with default error type
        rollback_and_clear_caches(mock_db)

        # Verify rollback was called
        mock_db.rollback.assert_called_once()

        # Verify caches were cleared
        assert cache_manager.get_cache_value("stamp", "test_tx1") is None

    def test_rollback_continues_even_if_clear_fails(self, mock_db):
        """Test that rollback happens even if cache clearing fails."""
        # Mock clear_all_caches to raise an exception
        with patch("index_core.blocks.clear_all_caches", side_effect=Exception("Cache clear failed")):
            # This should not raise an exception
            try:
                rollback_and_clear_caches(mock_db, "test")
            except Exception:
                pytest.fail("rollback_and_clear_caches should not raise exceptions")

        # Verify rollback was still called
        mock_db.rollback.assert_called_once()

    @pytest.mark.parametrize("error_type", ["consensus", "deadlock", "general", "custom_error"])
    def test_rollback_with_different_error_types(self, mock_db, error_type):
        """Test rollback_and_clear_caches with various error types."""
        with patch("index_core.blocks.clear_all_caches") as mock_clear:
            rollback_and_clear_caches(mock_db, error_type)

            # Verify both operations were called
            mock_db.rollback.assert_called_once()
            mock_clear.assert_called_once()

    def test_cache_manager_clear_all(self):
        """Test that clear_all_caches clears all cache data."""
        # Add some test data
        cache_manager.set_cache_value("stamp", "test1", {"data": "value1"})
        cache_manager.set_cache_value("block", "test2", 12345)

        # Verify data exists
        assert cache_manager.get_cache_value("stamp", "test1") is not None
        assert cache_manager.get_cache_value("block", "test2") is not None

        # Clear all caches
        clear_all_caches()

        # Verify all caches are empty
        assert cache_manager.get_cache_value("stamp", "test1") is None
        assert cache_manager.get_cache_value("block", "test2") is None
