"""
Test rollback functionality for stamp numbering to ensure no gaps occur.

This test verifies that when a rollback occurs, the stamp counter is properly
reset so that new stamps continue from the correct number without gaps.
"""

from unittest.mock import MagicMock, call, patch

import pytest

from index_core.caching import cache_manager
from index_core.database import get_next_stamp_number, purge_block_db


class TestRollbackStampNumbering:
    """Test suite for stamp numbering during rollback operations."""

    def setup_method(self):
        """Clear caches before each test."""
        cache_manager.clear_all()

    def test_stamp_counter_after_rollback(self):
        """Test that stamp counter is correctly reset after rollback."""
        # Mock database connection
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=None)

        # Simulate stamps in database before rollback
        # Stamps 1-10 exist, with stamp 10 at block 100
        mock_cursor.execute = MagicMock()
        mock_cursor.fetchone = MagicMock()

        # First, get_next_stamp_number should return 11 (MAX(stamp) + 1)
        mock_cursor.fetchone.return_value = (10,)
        next_stamp = get_next_stamp_number(mock_db, "stamp")
        assert next_stamp == 11

        # Now simulate rollback to block 95 (which should remove stamps 6-10)
        with patch("index_core.database.logger") as mock_logger:
            purge_block_db(mock_db, 95)

        # After rollback, database should only have stamps 1-5
        # So get_next_stamp_number should return 6, not 11
        mock_cursor.fetchone.return_value = (5,)
        next_stamp_after_rollback = get_next_stamp_number(mock_db, "stamp")
        assert (
            next_stamp_after_rollback == 6
        ), f"Expected stamp 6 after rollback, but got {next_stamp_after_rollback}. This would create a gap!"

    def test_cache_cleared_after_database_operations(self):
        """Test that caches are cleared AFTER database purge, not before."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=None)

        # Track the order of operations
        operation_order = []

        # Mock execute to track when database operations happen
        def mock_execute(query, params=None):
            operation_order.append(("db_operation", query[:50]))  # First 50 chars of query

        mock_cursor.execute = mock_execute

        # Mock clear_all_caches to track when it's called
        with patch("index_core.database.clear_all_caches") as mock_clear_caches:

            def track_cache_clear():
                operation_order.append(("cache_clear", "clear_all_caches"))

            mock_clear_caches.side_effect = track_cache_clear

            # Run purge_block_db
            with patch("index_core.database.logger"):
                purge_block_db(mock_db, 100)

            # Verify that all database operations happened before cache clear
            db_ops_indices = [i for i, (op_type, _) in enumerate(operation_order) if op_type == "db_operation"]
            cache_clear_indices = [i for i, (op_type, _) in enumerate(operation_order) if op_type == "cache_clear"]

            assert len(cache_clear_indices) == 1, "clear_all_caches should be called exactly once"
            assert len(db_ops_indices) > 0, "Database operations should occur"
            assert (
                max(db_ops_indices) < cache_clear_indices[0]
            ), "All database operations must complete before cache is cleared"

    def test_cursed_stamp_counter_after_rollback(self):
        """Test that cursed stamp counter is correctly reset after rollback."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor
        mock_db.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_db.cursor.return_value.__exit__ = MagicMock(return_value=None)

        # Simulate cursed stamps in database before rollback
        # Cursed stamps -1 to -5 exist, with -5 at block 100
        mock_cursor.execute = MagicMock()
        mock_cursor.fetchone = MagicMock()

        # First, get_next_stamp_number should return -6 (MIN(stamp) - 1)
        mock_cursor.fetchone.return_value = (-5,)
        next_stamp = get_next_stamp_number(mock_db, "cursed")
        assert next_stamp == -6

        # Now simulate rollback to block 95 (which should remove cursed stamps -3 to -5)
        with patch("index_core.database.logger") as mock_logger:
            purge_block_db(mock_db, 95)

        # After rollback, database should only have cursed stamps -1 to -2
        # So get_next_stamp_number should return -3, not -6
        mock_cursor.fetchone.return_value = (-2,)
        next_stamp_after_rollback = get_next_stamp_number(mock_db, "cursed")
        assert (
            next_stamp_after_rollback == -3
        ), f"Expected cursed stamp -3 after rollback, but got {next_stamp_after_rollback}. This would create a gap!"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
