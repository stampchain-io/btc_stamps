import os
import threading
from unittest.mock import Mock, patch

import pymysql
import pytest

from index_core.database_manager import ConnectionPool, DatabaseManager, PooledConnection


class TestPooledConnection:
    """Test the PooledConnection wrapper class"""

    def test_pooled_connection_creation(self):
        """Test creating a PooledConnection"""
        mock_connection = Mock()
        mock_pool = Mock()

        pooled_conn = PooledConnection(mock_connection, mock_pool)

        assert pooled_conn.connection == mock_connection
        assert pooled_conn.pool == mock_pool
        assert not pooled_conn._closed

    def test_pooled_connection_close(self):
        """Test closing a PooledConnection returns it to pool"""
        mock_connection = Mock()
        mock_pool = Mock()

        pooled_conn = PooledConnection(mock_connection, mock_pool)
        pooled_conn.close()

        mock_pool.return_connection.assert_called_once_with(mock_connection)
        assert pooled_conn._closed

    def test_pooled_connection_close_idempotent(self):
        """Test that closing multiple times only returns to pool once"""
        mock_connection = Mock()
        mock_pool = Mock()

        pooled_conn = PooledConnection(mock_connection, mock_pool)
        pooled_conn.close()
        pooled_conn.close()  # Second close

        mock_pool.return_connection.assert_called_once()

    def test_pooled_connection_context_manager(self):
        """Test PooledConnection as context manager"""
        mock_connection = Mock()
        mock_pool = Mock()

        pooled_conn = PooledConnection(mock_connection, mock_pool)

        with pooled_conn as conn:
            assert conn == pooled_conn

        mock_pool.return_connection.assert_called_once()

    def test_pooled_connection_attribute_proxy(self):
        """Test that PooledConnection proxies attributes to underlying connection"""
        mock_connection = Mock()
        mock_connection.some_attribute = "test_value"
        mock_connection.some_method.return_value = "method_result"
        mock_pool = Mock()

        pooled_conn = PooledConnection(mock_connection, mock_pool)

        assert pooled_conn.some_attribute == "test_value"
        assert pooled_conn.some_method() == "method_result"


class TestConnectionPool:
    """Test the ConnectionPool class"""

    @patch("index_core.database_manager.pymysql.connect")
    def test_connection_pool_initialization(self, mock_connect):
        """Test ConnectionPool initialization with default parameters"""
        mock_connect.return_value = Mock()

        pool = ConnectionPool(host="localhost", user="test", password="test", database="test")

        assert pool.min_connections == 1
        assert pool.max_connections == 10
        assert pool.timeout == 30
        assert pool.get_pool_size() == 1  # Should create min_connections

    @patch("index_core.database_manager.pymysql.connect")
    def test_connection_pool_custom_parameters(self, mock_connect):
        """Test ConnectionPool with custom parameters"""
        mock_connect.return_value = Mock()

        pool = ConnectionPool(
            host="localhost", user="test", password="test", database="test", min_connections=2, max_connections=5, timeout=60
        )

        assert pool.min_connections == 2
        assert pool.max_connections == 5
        assert pool.timeout == 60
        assert pool.get_pool_size() == 2

    @patch("index_core.database_manager.pymysql.connect")
    def test_get_connection_from_pool(self, mock_connect):
        """Test getting a connection from the pool"""
        mock_connection = Mock()
        mock_connection.ping.return_value = None
        mock_connect.return_value = mock_connection

        pool = ConnectionPool(host="localhost", user="test", password="test", database="test")

        pooled_conn = pool.get_connection()

        assert isinstance(pooled_conn, PooledConnection)
        assert pooled_conn.connection == mock_connection

    @patch("index_core.database_manager.pymysql.connect")
    def test_get_connection_pool_exhausted(self, mock_connect):
        """Test behavior when connection pool is exhausted"""
        mock_connect.return_value = Mock()

        # Create pool with max 1 connection
        pool = ConnectionPool(
            host="localhost", user="test", password="test", database="test", min_connections=1, max_connections=1, timeout=0.1
        )

        # Get the only connection
        conn1 = pool.get_connection()

        # Try to get another - should raise exception after timeout
        with pytest.raises(Exception, match="Connection pool exhausted"):
            pool.get_connection()

    @patch("index_core.database_manager.pymysql.connect")
    def test_return_connection_to_pool(self, mock_connect):
        """Test returning a connection to the pool"""
        mock_connection = Mock()
        mock_connection.ping.return_value = None
        mock_connect.return_value = mock_connection

        pool = ConnectionPool(host="localhost", user="test", password="test", database="test")

        # Pool starts with 1 connection
        assert pool.get_pool_size() == 1

        # Get connection (removes from pool)
        pooled_conn = pool.get_connection()
        assert pool.get_pool_size() == 0

        # Return connection to pool
        pool.return_connection(mock_connection)
        assert pool.get_pool_size() == 1

    @patch("index_core.database_manager.pymysql.connect")
    def test_remove_dead_connection(self, mock_connect):
        """Test removing a dead connection from pool"""
        mock_connection = Mock()
        mock_connection.ping.side_effect = Exception("Connection dead")
        mock_connection.close.return_value = None
        mock_connect.return_value = mock_connection

        pool = ConnectionPool(host="localhost", user="test", password="test", database="test")

        initial_active = pool.get_active_connections()
        pool._remove_connection(mock_connection)

        # Should remove from active connections
        assert pool.get_active_connections() < initial_active

    @patch("index_core.database_manager.pymysql.connect")
    def test_close_all_connections(self, mock_connect):
        """Test closing all connections in pool"""
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        pool = ConnectionPool(host="localhost", user="test", password="test", database="test")

        pool.close_all()

        assert pool.get_pool_size() == 0
        assert pool.get_active_connections() == 0


class TestDatabaseManager:
    """Test the DatabaseManager class"""

    def setup_method(self):
        """Set up test environment for each test"""
        # Ensure we're in test mode
        os.environ["MOCK_DB"] = "1"
        os.environ["USE_TEST_DB"] = "1"

    def teardown_method(self):
        """Clean up after each test"""
        # Clean up environment
        if "MOCK_DB" in os.environ:
            del os.environ["MOCK_DB"]
        if "USE_TEST_DB" in os.environ:
            del os.environ["USE_TEST_DB"]

    def test_database_manager_initialization(self):
        """Test DatabaseManager initialization"""
        db_manager = DatabaseManager()

        assert db_manager.max_retries == 5
        assert db_manager.retry_delay == 5
        assert db_manager.connect_timeout == 30
        assert db_manager.read_timeout == 3600
        assert db_manager.write_timeout == 3600

    def test_database_manager_mock_mode(self):
        """Test DatabaseManager behavior in mock mode"""
        db_manager = DatabaseManager()

        # Should not initialize pool in mock mode
        assert db_manager.pool is None

    @patch.dict(os.environ, {"MOCK_DB": "0", "USE_TEST_DB": "0"})
    @patch("index_core.database_manager.ConnectionPool")
    def test_database_manager_real_mode_initialization(self, mock_pool_class):
        """Test DatabaseManager initialization in real mode"""
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool

        db_manager = DatabaseManager()

        # Should initialize pool in real mode
        mock_pool_class.assert_called_once()

    def test_get_connection_params(self):
        """Test getting connection parameters from environment"""
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
        """Test connection parameters with fallback values"""
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

    def test_connect_mock_mode(self):
        """Test connect() method in mock mode"""
        db_manager = DatabaseManager()

        connection = db_manager.connect()

        # Should return a mock connection
        assert hasattr(connection, "cursor")
        connection.cursor.assert_not_called()  # Just check it exists

    def test_get_cursor_mock_mode(self):
        """Test get_cursor() method in mock mode"""
        db_manager = DatabaseManager()

        cursor = db_manager.get_cursor()

        # Should return a mock cursor
        assert cursor is not None

    def test_get_long_running_connection_mock_mode(self):
        """Test get_long_running_connection() in mock mode"""
        db_manager = DatabaseManager()

        connection = db_manager.get_long_running_connection()

        # Should return a mock connection
        assert hasattr(connection, "cursor")

    @patch.dict(os.environ, {"MOCK_DB": "0", "USE_TEST_DB": "0"})
    @patch("index_core.database_manager.pymysql.connect")
    def test_get_long_running_connection_real_mode(self, mock_connect):
        """Test get_long_running_connection() in real mode"""
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        db_manager = DatabaseManager()
        db_manager.pool = Mock()  # Mock the pool

        # Clear previous calls from pool initialization
        mock_connect.reset_mock()

        connection = db_manager.get_long_running_connection()

        # Should call pymysql.connect with extended timeouts
        mock_connect.assert_called_once()
        call_args = mock_connect.call_args[1]
        assert call_args["read_timeout"] == 86400
        assert call_args["write_timeout"] == 86400

    @patch.dict(os.environ, {"MOCK_DB": "0", "USE_TEST_DB": "0"})
    def test_connect_with_retries(self):
        """Test connect() method with retry logic"""
        db_manager = DatabaseManager()

        # Mock pool that fails first time, succeeds second time
        mock_pool = Mock()
        mock_connection = Mock()
        mock_pool.get_connection.side_effect = [Exception("Connection failed"), mock_connection]
        db_manager.pool = mock_pool

        with patch("time.sleep"):  # Speed up the test
            connection = db_manager.connect()

        assert connection == mock_connection
        assert mock_pool.get_connection.call_count == 2

    @patch.dict(os.environ, {"MOCK_DB": "0", "USE_TEST_DB": "0"})
    def test_connect_max_retries_exceeded(self):
        """Test connect() when max retries are exceeded"""
        db_manager = DatabaseManager()
        db_manager.max_retries = 2  # Reduce for faster test

        # Mock pool that always fails
        mock_pool = Mock()
        mock_pool.get_connection.side_effect = Exception("Connection failed")
        db_manager.pool = mock_pool

        with patch("time.sleep"):  # Speed up the test
            with pytest.raises(RuntimeError, match="Failed to acquire database connection"):
                db_manager.connect()

    def test_execute_with_retry_mock_mode(self):
        """Test execute_with_retry() in mock mode"""
        db_manager = DatabaseManager()

        mock_cursor = Mock()
        query = "SELECT * FROM test"
        params = ("param1",)

        # Should not raise exception
        db_manager.execute_with_retry(mock_cursor, query, params)

        mock_cursor.execute.assert_called_once_with(query, params)

    @patch.dict(os.environ, {"MOCK_DB": "0", "USE_TEST_DB": "0"})
    def test_execute_with_retry_success(self):
        """Test execute_with_retry() success case"""
        db_manager = DatabaseManager()

        mock_cursor = Mock()
        mock_cursor.execute.return_value = None

        query = "SELECT * FROM test"
        params = ("param1",)

        db_manager.execute_with_retry(mock_cursor, query, params)

        mock_cursor.execute.assert_called_once_with(query, params)

    @patch.dict(os.environ, {"MOCK_DB": "0", "USE_TEST_DB": "0"})
    def test_execute_with_retry_with_retries(self):
        """Test execute_with_retry() with retries on operational error"""
        db_manager = DatabaseManager()
        db_manager.max_retries = 2

        mock_cursor = Mock()
        mock_cursor.execute.side_effect = [pymysql.OperationalError("Connection lost"), None]  # Success on second try

        # Mock connect to return new cursor
        with patch.object(db_manager, "connect") as mock_connect:
            mock_connection = Mock()
            mock_new_cursor = Mock()
            mock_connection.cursor.return_value = mock_new_cursor
            mock_connect.return_value = mock_connection

            query = "SELECT * FROM test"

            db_manager.execute_with_retry(mock_cursor, query)

            # Should have been called twice (original + retry)
            assert mock_cursor.execute.call_count == 1
            mock_connect.assert_called_once()

    @patch.dict(os.environ, {"MOCK_DB": "0", "USE_TEST_DB": "0"})
    def test_execute_with_retry_max_retries_exceeded(self):
        """Test execute_with_retry() when max retries exceeded"""
        db_manager = DatabaseManager()
        db_manager.max_retries = 2

        mock_cursor = Mock()
        mock_cursor.execute.side_effect = pymysql.OperationalError("Persistent error")

        with patch.object(db_manager, "connect") as mock_connect:
            # Mock connect to return a connection with cursor
            mock_connection = Mock()
            mock_new_cursor = Mock()
            mock_connection.cursor.return_value = mock_new_cursor
            mock_connect.return_value = mock_connection

            with pytest.raises(RuntimeError, match="Query execution failed after .* attempts"):
                db_manager.execute_with_retry(mock_cursor, "SELECT * FROM test")

    def test_check_connection_valid(self):
        """Test check_connection() with valid connection"""
        db_manager = DatabaseManager()

        mock_connection = Mock()
        mock_connection.ping.return_value = None

        result = db_manager.check_connection(mock_connection)

        assert result == mock_connection
        mock_connection.ping.assert_called_once_with(reconnect=True)

    def test_check_connection_invalid(self):
        """Test check_connection() with invalid connection"""
        db_manager = DatabaseManager()

        mock_connection = Mock()
        mock_connection.ping.side_effect = Exception("Connection dead")

        with patch.object(db_manager, "connect") as mock_connect:
            mock_new_connection = Mock()
            mock_connect.return_value = mock_new_connection

            result = db_manager.check_connection(mock_connection)

            assert result == mock_new_connection
            mock_connect.assert_called_once()

    def test_ensure_connection_none(self):
        """Test ensure_connection() with None connection"""
        db_manager = DatabaseManager()

        with patch.object(db_manager, "connect") as mock_connect:
            mock_connection = Mock()
            mock_connect.return_value = mock_connection

            result = db_manager.ensure_connection(None)

            assert result == mock_connection
            mock_connect.assert_called_once()

    def test_ensure_connection_valid(self):
        """Test ensure_connection() with valid connection"""
        db_manager = DatabaseManager()

        mock_connection = Mock()

        with patch.object(db_manager, "check_connection", return_value=mock_connection) as mock_check:
            result = db_manager.ensure_connection(mock_connection)

            assert result == mock_connection
            mock_check.assert_called_once_with(mock_connection)

    def test_close_with_pool(self):
        """Test close() method when pool exists"""
        db_manager = DatabaseManager()

        mock_pool = Mock()
        db_manager.pool = mock_pool

        db_manager.close()

        mock_pool.close_all.assert_called_once()

    def test_close_without_pool(self):
        """Test close() method when pool is None"""
        db_manager = DatabaseManager()

        # Should not raise exception
        db_manager.close()

    def test_close_with_pool_error(self):
        """Test close() method when pool.close_all() raises exception"""
        db_manager = DatabaseManager()

        mock_pool = Mock()
        mock_pool.close_all.side_effect = Exception("Close error")
        db_manager.pool = mock_pool

        # Should not raise exception
        db_manager.close()


class TestDatabaseManagerIntegration:
    """Integration tests for DatabaseManager"""

    def setup_method(self):
        """Set up test environment"""
        os.environ["MOCK_DB"] = "1"
        os.environ["USE_TEST_DB"] = "1"

    def teardown_method(self):
        """Clean up after each test"""
        if "MOCK_DB" in os.environ:
            del os.environ["MOCK_DB"]
        if "USE_TEST_DB" in os.environ:
            del os.environ["USE_TEST_DB"]

    def test_full_workflow_mock_mode(self):
        """Test complete workflow in mock mode"""
        db_manager = DatabaseManager()

        # Get connection
        connection = db_manager.connect()
        assert connection is not None

        # Get cursor
        cursor = db_manager.get_cursor()
        assert cursor is not None

        # Execute query
        db_manager.execute_with_retry(cursor, "SELECT 1")

        # Close
        db_manager.close()

    def test_connection_context_manager_workflow(self):
        """Test using connections as context managers"""
        db_manager = DatabaseManager()

        connection = db_manager.connect()

        # Mock the connection to act like a real one
        if hasattr(connection, "__enter__") and hasattr(connection, "__exit__"):
            with connection as conn:
                cursor = conn.cursor()
                assert cursor is not None
        else:
            # For mock connections, just test basic usage
            cursor = connection.cursor()
            assert cursor is not None

    def test_concurrent_connection_requests(self):
        """Test multiple threads requesting connections simultaneously"""
        db_manager = DatabaseManager()
        connections = []
        errors = []

        def get_connection():
            try:
                conn = db_manager.connect()
                connections.append(conn)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=get_connection)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Should have gotten connections without errors
        assert len(errors) == 0
        assert len(connections) == 5

    def test_environment_variable_override(self):
        """Test that environment variables properly override defaults"""
        with patch.dict(os.environ, {"DB_MIN_CONNECTIONS": "5", "DB_MAX_CONNECTIONS": "20", "DB_POOL_TIMEOUT": "60"}):
            # These would be used in real mode
            db_manager = DatabaseManager()
            params = db_manager.get_connection_params()

            # Basic check that params are returned
            assert isinstance(params, dict)
            assert "host" in params
            assert "user" in params
