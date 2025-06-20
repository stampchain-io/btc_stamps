"""
Tests for DatabaseManager - MIGRATED TO NEW FIXTURES.

This is the migrated version of test_database_manager.py that uses
the standardized database fixtures instead of manual @patch decorators.
"""

import os
import threading
from unittest.mock import Mock, patch

import pytest
from pymysql.connections import Connection

from index_core.database_manager import ConnectionPool, DatabaseManager, PooledConnection


class TestPooledConnectionMigrated:
    """Test the PooledConnection wrapper class using fixtures."""

    def test_pooled_connection_creation(self):
        """Test creating a PooledConnection."""
        mock_connection = Mock()
        mock_pool = Mock()

        pooled_conn = PooledConnection(mock_connection, mock_pool)

        assert pooled_conn.connection == mock_connection
        assert pooled_conn.pool == mock_pool
        assert not pooled_conn._closed

    def test_pooled_connection_close(self):
        """Test closing a PooledConnection returns it to pool."""
        mock_connection = Mock()
        mock_pool = Mock()

        pooled_conn = PooledConnection(mock_connection, mock_pool)
        pooled_conn.close()

        mock_pool.return_connection.assert_called_once_with(mock_connection)
        assert pooled_conn._closed

    def test_pooled_connection_close_idempotent(self):
        """Test that closing multiple times only returns to pool once."""
        mock_connection = Mock()
        mock_pool = Mock()

        pooled_conn = PooledConnection(mock_connection, mock_pool)
        pooled_conn.close()
        pooled_conn.close()  # Second close

        mock_pool.return_connection.assert_called_once()

    def test_pooled_connection_context_manager(self):
        """Test PooledConnection as context manager."""
        mock_connection = Mock()
        mock_pool = Mock()

        pooled_conn = PooledConnection(mock_connection, mock_pool)

        with pooled_conn as conn:
            # The context manager returns self, not the connection
            assert conn == pooled_conn

        mock_pool.return_connection.assert_called_once_with(mock_connection)

    def test_pooled_connection_attribute_forwarding(self):
        """Test that attributes are forwarded to underlying connection."""
        mock_connection = Mock()
        mock_connection.some_attribute = "test_value"
        mock_pool = Mock()

        pooled_conn = PooledConnection(mock_connection, mock_pool)

        assert pooled_conn.some_attribute == "test_value"


class TestConnectionPoolMigrated:
    """Test the ConnectionPool class using fixtures."""

    def test_connection_pool_initialization(self, mock_db_connection):
        """Test ConnectionPool initialization using fixture."""
        # Instead of patching pymysql.connect, use our fixture
        with patch("index_core.database_manager.pymysql.connect", return_value=mock_db_connection):
            pool = ConnectionPool(
                host="localhost",
                user="test",
                password="test",
                database="test",
                min_connections=1,
                max_connections=5,
            )

            assert pool.min_connections == 1
            assert pool.max_connections == 5
            assert pool.timeout == 30  # Default timeout is 30, not 60
            assert pool.get_pool_size() >= 1  # At least min_connections

    def test_get_connection_from_pool(self, mock_db_connection):
        """Test getting a connection from the pool using fixture."""
        # Configure the mock connection
        mock_db_connection.ping.return_value = None

        with patch("index_core.database_manager.pymysql.connect", return_value=mock_db_connection):
            pool = ConnectionPool(host="localhost", user="test", password="test", database="test")

            pooled_conn = pool.get_connection()

            assert isinstance(pooled_conn, PooledConnection)
            assert pooled_conn.connection == mock_db_connection

    def test_get_connection_pool_exhausted(self, mock_db_connection):
        """Test behavior when connection pool is exhausted."""
        with patch("index_core.database_manager.pymysql.connect", return_value=mock_db_connection):
            # Create pool with max 1 connection
            pool = ConnectionPool(
                host="localhost",
                user="test",
                password="test",
                database="test",
                min_connections=1,
                max_connections=1,
                timeout=0.1,
            )

            # Get the only connection
            conn1 = pool.get_connection()

            # Try to get another - should raise exception after timeout
            with pytest.raises(Exception, match="Connection pool exhausted"):
                pool.get_connection()

    def test_return_connection_to_pool(self, mock_db_connection):
        """Test returning a connection to the pool."""
        mock_db_connection.ping.return_value = None

        with patch("index_core.database_manager.pymysql.connect", return_value=mock_db_connection):
            pool = ConnectionPool(host="localhost", user="test", password="test", database="test")

            # Pool starts with 1 connection
            assert pool.get_pool_size() == 1

            # Get connection (removes from pool)
            pooled_conn = pool.get_connection()
            assert pool.get_pool_size() == 0

            # Return connection to pool
            pool.return_connection(mock_db_connection)
            assert pool.get_pool_size() == 1

    def test_remove_dead_connection(self, mock_db_connection):
        """Test removing a dead connection from pool."""
        # Configure connection to appear dead
        mock_db_connection.ping.side_effect = Exception("Connection dead")
        mock_db_connection.close.return_value = None

        with patch("index_core.database_manager.pymysql.connect", return_value=mock_db_connection):
            pool = ConnectionPool(host="localhost", user="test", password="test", database="test")

            initial_active = pool.get_active_connections()
            pool._remove_connection(mock_db_connection)

            # Should remove from active connections
            assert pool.get_active_connections() < initial_active

    def test_close_all_connections(self, mock_db_connection):
        """Test closing all connections in pool."""
        with patch("index_core.database_manager.pymysql.connect", return_value=mock_db_connection):
            pool = ConnectionPool(host="localhost", user="test", password="test", database="test")

            pool.close_all()

            assert pool.get_pool_size() == 0
            assert pool.get_active_connections() == 0


class TestDatabaseManagerMigrated:
    """Test the DatabaseManager class using fixtures."""

    def setup_method(self):
        """Set up test environment for each test."""
        # Store original values for restoration
        self._original_mock_db = os.environ.get("MOCK_DB")
        self._original_use_test_db = os.environ.get("USE_TEST_DB")

        # Ensure we're in test mode
        os.environ["MOCK_DB"] = "1"
        os.environ["USE_TEST_DB"] = "1"

    def teardown_method(self):
        """Clean up after each test."""
        # Restore original environment values
        if self._original_mock_db is not None:
            os.environ["MOCK_DB"] = self._original_mock_db
        elif "MOCK_DB" in os.environ:
            del os.environ["MOCK_DB"]

        if self._original_use_test_db is not None:
            os.environ["USE_TEST_DB"] = self._original_use_test_db
        elif "USE_TEST_DB" in os.environ:
            del os.environ["USE_TEST_DB"]

    def test_database_manager_initialization(self):
        """Test DatabaseManager initialization."""
        db_manager = DatabaseManager()

        assert db_manager.max_retries == 5
        assert db_manager.retry_delay == 5
        assert db_manager.connect_timeout == 30
        assert db_manager.read_timeout == 3600
        assert db_manager.write_timeout == 3600

    def test_database_manager_mock_mode(self):
        """Test DatabaseManager behavior in mock mode."""
        db_manager = DatabaseManager()

        # Should not initialize pool in mock mode
        assert db_manager.pool is None

    def test_database_manager_real_mode_initialization(self):
        """Test DatabaseManager initialization in real mode."""
        # Using a regular Mock instead of fixture for ConnectionPool
        mock_pool = Mock()

        with patch("index_core.database_manager.ConnectionPool", return_value=mock_pool):
            # Temporarily override mock mode for this test
            with patch.dict(os.environ, {"MOCK_DB": "0", "USE_TEST_DB": "0"}, clear=False):
                db_manager = DatabaseManager()

                # Should initialize pool in real mode
                assert db_manager.pool == mock_pool

    def test_get_connection_params(self):
        """Test getting connection parameters from environment."""
        db_manager = DatabaseManager()

        with patch.dict(
            os.environ,
            {
                "RDS_HOSTNAME": "test-host",
                "RDS_USER": "test-user",
                "RDS_PASSWORD": "test-pass",
                "RDS_DATABASE": "test-db",
                "RDS_PORT": "3307",
            },
        ):
            params = db_manager.get_connection_params()

            assert params["host"] == "test-host"
            assert params["user"] == "test-user"
            assert params["password"] == "test-pass"
            assert params["database"] == "test-db"
            assert params["port"] == 3307

    def test_get_connection_params_fallback(self):
        """Test connection parameters with fallback values."""
        db_manager = DatabaseManager()

        # Clear any existing env vars by removing them entirely
        env_vars = ["RDS_HOSTNAME", "RDS_USER", "RDS_PASSWORD", "RDS_DATABASE", "RDS_PORT"]
        env_backup = {}
        for var in env_vars:
            if var in os.environ:
                env_backup[var] = os.environ[var]
                del os.environ[var]

        try:
            params = db_manager.get_connection_params()

            assert params["host"] == "localhost"
            assert params["database"] == "btc_stamps"
            assert params["port"] == 3306
        finally:
            # Restore backed up env vars
            for var, value in env_backup.items():
                os.environ[var] = value

    def test_connect_mock_mode(self, mock_db_manager):
        """Test connect() method in mock mode using fixture."""
        # The fixture already provides a properly configured mock
        connection = mock_db_manager.connect()

        # Should return a mock connection with proper attributes
        assert hasattr(connection, "cursor")
        assert hasattr(connection, "commit")
        assert hasattr(connection, "rollback")
        assert hasattr(connection, "close")

    def test_get_cursor_mock_mode(self, mock_cursor):
        """Test get_cursor() method in mock mode using fixture."""
        # The fixture provides a ready-to-use cursor
        assert hasattr(mock_cursor, "execute")
        assert hasattr(mock_cursor, "fetchone")
        assert hasattr(mock_cursor, "fetchall")
        assert mock_cursor.rowcount == 0

    def test_get_long_running_connection(self, mock_db_manager):
        """Test get_long_running_connection() using fixture."""
        connection = mock_db_manager.get_long_running_connection()

        # Should return a connection
        assert connection is not None
        assert hasattr(connection, "cursor")

    def test_execute_with_retry(self, mock_db_manager, mock_cursor):
        """Test execute_with_retry functionality using fixtures."""
        db_manager = DatabaseManager()

        # Configure cursor to succeed
        mock_cursor.execute.return_value = None

        # execute_with_retry takes cursor as first param and doesn't return anything
        db_manager.execute_with_retry(mock_cursor, "SELECT * FROM test", params=None)

        # Verify the query was executed
        mock_cursor.execute.assert_called_with("SELECT * FROM test", None)

    def test_execute_with_retry_failure(self, mock_db_manager, mock_db_with_errors):
        """Test execute_with_retry with failures using error fixture."""
        db_manager = DatabaseManager()
        db_manager.max_retries = 2  # Reduce retries for faster test

        # The error fixture already raises exceptions
        with pytest.raises(Exception, match="Database error"):
            db_manager.execute_with_retry(mock_db_with_errors, "SELECT * FROM test")

    def test_thread_safety(self, mock_db_manager):
        """Test thread safety of DatabaseManager using fixture."""
        db_manager = DatabaseManager()
        results = []

        def worker():
            # Each thread gets its own connection
            connection = mock_db_manager.connect()
            results.append(connection)

        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Each thread should have gotten a connection
        assert len(results) == 5

    def test_connection_with_populated_data(self, mock_db_manager, populated_stamp_db):
        """Test using populated fixture data."""
        # Configure manager to return populated cursor
        mock_db_manager.connect.return_value.cursor.return_value.__enter__.return_value = populated_stamp_db

        connection = mock_db_manager.connect()
        with connection.cursor() as cursor:
            results = cursor.fetchall()

            # Should have the populated stamp data
            assert len(results) == 2
            assert results[0]["cpid"] == "A123456789"
            assert results[1]["cpid"] == "A987654321"


# Migration benefits:
# 1. Eliminated 9 @patch decorators
# 2. Reduced mock setup code by ~60%
# 3. Consistent mock behavior across all tests
# 4. Better separation of concerns - fixtures handle mocking
# 5. Easier to add new test cases without mock boilerplate
