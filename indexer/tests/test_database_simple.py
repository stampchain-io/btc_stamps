"""Tests for simple database functions."""

import unittest
from unittest.mock import MagicMock, call, patch

from index_core.database import (
    get_stamp_view_count,
    get_stamp_view_stats,
    get_unlocked_cpids,
    increment_stamp_view_count,
    purge_owners,
)
from index_core.exceptions import DatabaseInsertError


class TestSimpleDatabaseFunctions(unittest.TestCase):
    """Test simple database functions that are easy to test."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_db = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_db.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_db.cursor.return_value.__exit__.return_value = None

    def test_increment_stamp_view_count_success(self):
        """Test incrementing stamp view count - success case."""
        stamp_id = 12345

        increment_stamp_view_count(self.mock_db, stamp_id)

        # Check the query was executed correctly
        self.mock_cursor.execute.assert_called_once()
        query = self.mock_cursor.execute.call_args[0][0]
        params = self.mock_cursor.execute.call_args[0][1]

        self.assertIn("INSERT INTO", query)
        self.assertIn("ON DUPLICATE KEY UPDATE", query)
        self.assertEqual(params, (stamp_id,))

        # Check commit was called
        self.mock_db.commit.assert_called_once()

    def test_increment_stamp_view_count_error(self):
        """Test incrementing stamp view count - database error."""
        stamp_id = 12345
        self.mock_cursor.execute.side_effect = Exception("DB Error")

        with self.assertRaises(DatabaseInsertError) as context:
            increment_stamp_view_count(self.mock_db, stamp_id)

        self.assertIn("Failed to increment view count", str(context.exception))
        self.mock_db.rollback.assert_called_once()

    def test_get_stamp_view_count_success(self):
        """Test getting stamp view count - success case."""
        stamp_id = 12345
        self.mock_cursor.fetchone.return_value = (42,)

        count = get_stamp_view_count(self.mock_db, stamp_id)

        self.assertEqual(count, 42)
        self.mock_cursor.execute.assert_called_once()
        query = self.mock_cursor.execute.call_args[0][0]
        params = self.mock_cursor.execute.call_args[0][1]

        self.assertIn("SELECT view_count", query)
        self.assertIn("FROM stamp_views", query)
        self.assertEqual(params, (stamp_id,))

    def test_get_stamp_view_count_not_found(self):
        """Test getting stamp view count - stamp not found."""
        stamp_id = 99999
        self.mock_cursor.fetchone.return_value = None

        count = get_stamp_view_count(self.mock_db, stamp_id)

        self.assertEqual(count, 0)

    def test_get_stamp_view_count_error(self):
        """Test getting stamp view count - database error."""
        stamp_id = 12345
        self.mock_cursor.execute.side_effect = Exception("DB Error")

        count = get_stamp_view_count(self.mock_db, stamp_id)

        self.assertEqual(count, 0)  # Returns 0 on error

    def test_get_unlocked_cpids_success(self):
        """Test getting unlocked CPIDs - success case."""
        mock_results = [
            ("STAMP:A1:1",),
            ("STAMP:A1:2",),
            ("STAMP:A1:3",),
        ]
        self.mock_cursor.fetchall.return_value = mock_results

        cpids = get_unlocked_cpids(self.mock_db)

        self.assertEqual(cpids, mock_results)
        self.mock_cursor.execute.assert_called_once()
        query = self.mock_cursor.execute.call_args[0][0]

        self.assertIn("SELECT DISTINCT cpid FROM", query)
        self.assertIn("WHERE locked != 1", query)

    def test_get_unlocked_cpids_empty(self):
        """Test getting unlocked CPIDs - no results."""
        self.mock_cursor.fetchall.return_value = []

        cpids = get_unlocked_cpids(self.mock_db)

        self.assertEqual(cpids, [])

    def test_purge_owners(self):
        """Test purging owners table."""
        cursor = self.mock_cursor

        purge_owners(cursor)

        cursor.execute.assert_called_once_with("TRUNCATE TABLE owners")

    def test_get_stamp_view_stats_success(self):
        """Test getting stamp view statistics - success case."""
        self.mock_cursor.fetchone.return_value = (25, 1500, 60.0)

        stats = get_stamp_view_stats(self.mock_db)

        self.assertEqual(stats["total_stamps_with_views"], 25)
        self.assertEqual(stats["total_views"], 1500)
        self.assertEqual(stats["avg_views_per_stamp"], 60.0)

        self.mock_cursor.execute.assert_called_once()
        query = self.mock_cursor.execute.call_args[0][0]
        self.assertIn("SUM(view_count)", query)
        self.assertIn("COUNT(*)", query)
        self.assertIn("AVG(view_count)", query)

    def test_get_stamp_view_stats_empty(self):
        """Test getting stamp view statistics - no data."""
        self.mock_cursor.fetchone.return_value = (0, 0, None)

        stats = get_stamp_view_stats(self.mock_db)

        self.assertEqual(stats["total_stamps_with_views"], 0)
        self.assertEqual(stats["total_views"], 0)
        self.assertEqual(stats["avg_views_per_stamp"], 0.0)

    def test_get_stamp_view_stats_error(self):
        """Test getting stamp view statistics - database error."""
        self.mock_cursor.execute.side_effect = Exception("DB Error")

        stats = get_stamp_view_stats(self.mock_db)

        # Should return default values on error
        self.assertEqual(stats["total_stamps_with_views"], 0)
        self.assertEqual(stats["total_views"], 0)
        self.assertEqual(stats["avg_views_per_stamp"], 0.0)


class TestDatabaseHelperFunctions(unittest.TestCase):
    """Test database helper functions."""

    @patch("index_core.database.db_manager")
    def test_reset_all_caches(self, mock_db_manager):
        """Test resetting all caches."""
        from index_core.database import reset_all_caches

        with patch("index_core.database.cache_manager") as mock_cache_manager:
            reset_all_caches()
            mock_cache_manager.clear_all.assert_called_once()

    @patch("index_core.database.db_manager")
    def test_check_db_connection_success(self, mock_db_manager):
        """Test checking database connection - success."""
        from index_core.database import check_db_connection

        mock_db = MagicMock()
        mock_db_manager.ensure_connection.return_value = mock_db

        result = check_db_connection(mock_db)

        self.assertEqual(result, mock_db)
        mock_db_manager.ensure_connection.assert_called_once_with(mock_db)

    @patch("index_core.database.db_manager")
    def test_check_db_connection_error(self, mock_db_manager):
        """Test checking database connection - error."""
        from index_core.database import check_db_connection

        mock_db = MagicMock()
        mock_db_manager.ensure_connection.side_effect = Exception("Connection failed")

        with self.assertRaises(Exception) as context:
            check_db_connection(mock_db)

        self.assertIn("Connection failed", str(context.exception))


if __name__ == "__main__":
    unittest.main()
