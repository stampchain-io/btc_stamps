"""
Example test file showing how to use the new database fixtures.

This demonstrates the before/after of refactoring tests to use standardized fixtures.
"""

import pytest


class TestDatabaseFixturesExample:
    """Example tests using the new database fixtures."""

    def test_using_mock_db_manager(self, mock_db_manager):
        """Example of using the mock_db_manager fixture."""
        # The fixture provides a pre-configured mock DatabaseManager
        connection = mock_db_manager.connect()

        # Verify the mock is properly configured
        assert connection is not None
        assert hasattr(connection, "cursor")
        assert hasattr(connection, "commit")
        assert hasattr(connection, "rollback")

        # Use the connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM stamps WHERE cpid = %s", ("A123456789",))
            # The cursor is a mock, so we can assert on calls
            cursor.execute.assert_called_once()

    def test_using_populated_stamp_db(self, populated_stamp_db):
        """Example of using pre-populated stamp data."""
        # The fixture provides a cursor with sample stamp data
        cursor = populated_stamp_db

        # Execute a query
        cursor.execute("SELECT * FROM stamps")
        results = cursor.fetchall()

        # The fixture has pre-configured the response
        assert len(results) == 2
        assert results[0]["cpid"] == "A123456789"
        assert results[0]["stamp"] == "STAMPY"

    def test_using_populated_src20_db(self, populated_src20_db):
        """Example of using pre-populated SRC-20 data."""
        cursor = populated_src20_db

        # Query for SRC-20 data
        cursor.execute("SELECT * FROM src20 WHERE tick = %s", ("STAMP",))
        results = cursor.fetchall()

        # The fixture provides sample SRC-20 transactions
        assert len(results) == 2
        assert results[0]["op"] == "DEPLOY"
        assert results[1]["op"] == "MINT"

    def test_error_handling(self, mock_db_with_errors):
        """Example of testing error handling with the error fixture."""
        cursor = mock_db_with_errors

        # The fixture is configured to raise errors
        with pytest.raises(Exception) as exc_info:
            cursor.execute("SELECT * FROM stamps")

        assert "Database error" in str(exc_info.value)

    def test_transaction_rollback(self, mock_db_connection):
        """Example of testing transaction behavior."""
        # Test transaction with error
        with mock_db_connection.cursor() as cursor:
            cursor.execute("INSERT INTO stamps ...")
            # Simulate an error that would trigger rollback
            mock_db_connection.rollback()

        # Verify rollback was called
        mock_db_connection.rollback.assert_called_once()
        mock_db_connection.commit.assert_not_called()

    def test_assert_database_called_helper(self, mock_cursor, assert_database_called):
        """Example of using the assertion helper."""
        # Perform some database operations
        mock_cursor.execute("SELECT * FROM stamps WHERE cpid = %s", ("A123456789",))

        # Use the helper to verify the call
        assert_database_called(mock_cursor, expected_query="SELECT * FROM stamps", expected_params=("A123456789",), times=1)


# Comparison with old style (before fixtures)
class TestOldStyleExample:
    """Example of how tests were written before standardized fixtures."""

    def test_old_style_database_mock(self):
        """Old style: manually creating mocks in each test."""
        from unittest.mock import MagicMock, Mock

        # Manual mock setup required in every test
        mock_db_manager = Mock()
        mock_db = Mock()
        mock_cursor = Mock()

        # Setup cursor context manager
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = mock_cursor
        cursor_context.__exit__.return_value = None

        # Configure mocks
        mock_db.cursor.return_value = cursor_context
        mock_db_manager.connect.return_value = mock_db
        mock_cursor.fetchall.return_value = []

        # Now we can use it...
        # (This setup was repeated in many test files!)

    # With fixtures, all this boilerplate is eliminated!
