"""Database connection management and pooling for PyMySQL."""

import logging
import os
import queue
import socket
import threading
import time
from typing import Dict, Optional

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import Cursor

logger = logging.getLogger(__name__)


def _apply_socket_keepalive(connection: Connection) -> None:
    """Enable TCP keepalive on a pymysql connection so the kernel detects
    a dead RDS endpoint within minutes instead of waiting for the default
    ~2-hour Linux idle timeout. Without this, a worker mid-recv() when RDS
    is killed (e.g. storage-full shutdown) can hang on the dead socket
    long past the application read_timeout.
    """
    try:
        sock = connection._sock  # type: ignore[attr-defined]  # pymysql doesn't expose this in stubs
        if sock is None:
            return
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # Idle 60s → first probe; probes every 10s × 6 → ~2 min to FIN a dead peer.
        if hasattr(socket, "TCP_KEEPIDLE"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
        if hasattr(socket, "TCP_KEEPINTVL"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
        if hasattr(socket, "TCP_KEEPCNT"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 6)
    except Exception as e:
        logger.debug(f"Could not apply TCP keepalive to connection: {e}")


class PooledConnection:
    """Wrapper for a database connection that returns it to the pool on close."""

    def __init__(self, connection: Connection, pool: "ConnectionPool"):
        self.connection = connection
        self.pool = pool
        self._closed = False

    def close(self):
        """Return the connection to the pool instead of closing it."""
        if not self._closed:
            self.pool.return_connection(self.connection)
            self._closed = True

    def __getattr__(self, name):
        """Proxy all other attributes to the underlying connection."""
        return getattr(self.connection, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class ConnectionPool:
    """A simple connection pool implementation."""

    def __init__(self, **kwargs):
        self.connection_params = kwargs
        self.min_connections = kwargs.pop("min_connections", 1)
        self.max_connections = kwargs.pop("max_connections", 10)
        self.timeout = kwargs.pop("timeout", 30)

        self._pool = queue.Queue(maxsize=self.max_connections)
        self._active_connections: Dict[int, Connection] = {}
        self._lock = threading.Lock()
        self._shutting_down = False
        self._initialize_pool()

    def _initialize_pool(self):
        """Create initial connections."""
        for _ in range(self.min_connections):
            connection = self._create_connection()
            if connection:
                self._pool.put(connection)

    def _create_connection(self) -> Optional[Connection]:
        """Create a new database connection."""
        try:
            connection = pymysql.connect(**self.connection_params)
            _apply_socket_keepalive(connection)
            with self._lock:
                self._active_connections[id(connection)] = connection
            return connection
        except Exception as e:
            logger.error(f"Error creating database connection: {e}")
            return None

    def get_connection(self) -> Optional[PooledConnection]:
        """Get a connection from the pool or create a new one if needed."""
        try:
            # Try to get a connection from the pool
            connection = self._pool.get(timeout=self.timeout)

            # Verify the connection is still alive. Pre-ping with a tight
            # timeout so a half-dead socket (e.g. RDS killed without sending
            # RST) doesn't hang the borrower for the full read_timeout.
            try:
                connection.ping(reconnect=False)
            except Exception as e:
                logger.info(f"Pool: evicting stale connection ({e}); reconnecting")
                self._remove_connection(connection)
                connection = self._create_connection()

            if connection:
                return PooledConnection(connection, self)

        except queue.Empty:
            # Pool is empty, try to create a new connection if under max_connections
            with self._lock:
                if len(self._active_connections) < self.max_connections:
                    connection = self._create_connection()
                    if connection:
                        return PooledConnection(connection, self)

            # If we reach here, we've hit the connection limit
            raise Exception("Connection pool exhausted")

        return None

    def return_connection(self, connection: Connection):
        """Return a connection to the pool."""
        if not connection:
            return

        try:
            # Verify the connection is still usable before returning to pool.
            # reconnect=False — if the socket is dead we'd rather evict than
            # block the returner on a re-handshake; the next borrower will
            # create a fresh connection via _create_connection().
            connection.ping(reconnect=False)
            self._pool.put(connection, timeout=self.timeout)
        except Exception as e:
            logger.info(f"Pool: ping failed on return ({e}); evicting")
            self._remove_connection(connection)

    def _remove_connection(self, connection: Connection):
        """Remove a connection from the active connections and create a new one if needed."""
        if not connection:
            return

        with self._lock:
            conn_id = id(connection)
            if conn_id in self._active_connections:
                try:
                    connection.close()
                except Exception:
                    pass
                del self._active_connections[conn_id]

        # Create a new connection to replace the removed one if we're below min_connections
        # But only if we're not shutting down
        if not getattr(self, "_shutting_down", False) and self.get_pool_size() < self.min_connections:
            new_conn = self._create_connection()
            if new_conn:
                self._pool.put(new_conn)

    def get_pool_size(self) -> int:
        """Get the current number of connections in the pool."""
        return self._pool.qsize()

    def get_active_connections(self) -> int:
        """Get the current number of active connections."""
        with self._lock:
            return len(self._active_connections)

    def close_all(self):
        """Close all connections in the pool."""
        # Set shutdown flag to prevent recreating connections
        self._shutting_down = True

        # Close all pooled connections
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                self._close_connection_directly(conn)
            except queue.Empty:
                break

        # Close all active connections
        with self._lock:
            for conn in list(self._active_connections.values()):
                try:
                    self._close_connection_directly(conn)
                except Exception:
                    pass
            self._active_connections.clear()

    def _close_connection_directly(self, connection: Connection):
        """Close a connection without maintaining pool minimums."""
        if not connection:
            return

        with self._lock:
            conn_id = id(connection)
            if conn_id in self._active_connections:
                try:
                    connection.close()
                except Exception:
                    pass
                del self._active_connections[conn_id]


class DatabaseManager:
    # Process-wide singleton: every `DatabaseManager()` call returns the same
    # instance so the connection pool is shared across all components. Without
    # this, each of the ~17 callers spun up its own ConnectionPool with its own
    # min_connections eager-init, multiplying total connections by ~17x and
    # exhausting RDS max_connections.
    _instance: Optional["DatabaseManager"] = None
    _singleton_lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self.__class__._initialized:
            return
        with self.__class__._singleton_lock:
            if self.__class__._initialized:
                return
            self.max_retries = 5
            self.retry_delay = 5
            self.connect_timeout = 30
            # Pool connections handle short queries (market data, lookups,
            # block-loop writes). A 1-hour read_timeout used to mask dead
            # sockets — when RDS was killed mid-recv(), workers hung up to
            # an hour. 5 min covers every legitimate pool query; long ops
            # (reparse, rebuild, sales_history) use get_long_running_connection().
            self.read_timeout = int(os.environ.get("DB_READ_TIMEOUT", "300"))
            self.write_timeout = int(os.environ.get("DB_WRITE_TIMEOUT", "300"))
            self.pool = None
            self._initialize_pool()
            self.__class__._initialized = True

    @classmethod
    def _reset_for_testing(cls) -> None:
        """Clear singleton state. Test-only — production code must not call this."""
        with cls._singleton_lock:
            if cls._instance is not None and getattr(cls._instance, "pool", None) is not None:
                try:
                    cls._instance.pool.close_all()
                except Exception:
                    pass
            cls._instance = None
            cls._initialized = False

    def _initialize_pool(self):
        """Initialize the connection pool with parameters from environment."""
        # Skip pool initialization if we're in test mode with mock DB
        if os.environ.get("MOCK_DB") == "1" or os.environ.get("USE_TEST_DB") == "1":
            logger.info("Using mock database for testing")
            return

        pool_params = self.get_connection_params()
        pool_params.update(
            {
                "min_connections": int(os.environ.get("DB_MIN_CONNECTIONS", "3")),
                "max_connections": int(os.environ.get("DB_MAX_CONNECTIONS", "10")),
                "timeout": int(os.environ.get("DB_POOL_TIMEOUT", "30")),
            }
        )
        self.pool = ConnectionPool(**pool_params)

    def get_connection_params(self) -> dict:
        """Get database connection parameters from environment."""

        params = {
            "host": os.environ.get("RDS_HOSTNAME", "localhost"),
            "user": os.environ.get("RDS_USER") or os.environ.get("MYSQL_USER", "admin"),
            "password": os.environ.get("RDS_PASSWORD") or os.environ.get("MYSQL_PASSWORD", "password"),
            "database": os.environ.get("RDS_DATABASE", "btc_stamps"),
            "port": int(os.environ.get("RDS_PORT", 3306)),
            "connect_timeout": self.connect_timeout,
            "read_timeout": self.read_timeout,
            "write_timeout": self.write_timeout,
            "charset": "utf8mb4",
            "autocommit": False,
            "client_flag": pymysql.constants.CLIENT.MULTI_STATEMENTS,
            # Do NOT override SESSION wait_timeout — let the server's global
            # wait_timeout reap idle pool connections. Previously this forced
            # 8h per-session, which made idle/leaked connections immortal until
            # the indexer process restarted.
            "init_command": "SET SESSION max_execution_time=3600000",
        }

        return params

    def get_long_running_connection(self) -> Connection:
        """Get a dedicated connection with extended timeouts for long operations"""
        # Return a mock connection if we're in test mode
        if os.environ.get("MOCK_DB") == "1" or os.environ.get("USE_TEST_DB") == "1":
            from unittest.mock import MagicMock

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            logger.info("Returning mock long-running database connection for testing")
            return mock_conn

        params = self.get_connection_params()
        params.update(
            {
                "read_timeout": 86400,
                "write_timeout": 86400,
                # Long-running ops legitimately need longer than the default
                # server wait_timeout. 2h covers reparse/snapshot/rebuild paths
                # without making leaks immortal (was 24h).
                "init_command": "SET SESSION wait_timeout=7200, max_execution_time=8640000",
            }
        )
        connection = pymysql.connect(**params)
        _apply_socket_keepalive(connection)
        return connection

    def connect(self) -> Connection:
        """Get a connection from the pool with retries."""
        # Return a mock connection if we're in test mode
        if os.environ.get("MOCK_DB") == "1" or os.environ.get("USE_TEST_DB") == "1":
            from unittest.mock import MagicMock

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            logger.info("Returning mock database connection for testing")
            return mock_conn

        last_error = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Attempting to acquire database connection (attempt {attempt + 1}/{self.max_retries})")
                start_time = time.time()
                connection = self.pool.get_connection()
                elapsed_time = time.time() - start_time
                if connection:
                    logger.debug(f"Database connection acquired from pool in {elapsed_time:.2f}s")
                    return connection
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    logger.warning(
                        f"Database connection attempt {attempt + 1} failed: {e}. Retrying in {wait_time} seconds..."
                    )
                    time.sleep(wait_time)

        logger.error(f"Failed to acquire database connection after {self.max_retries} attempts")
        raise RuntimeError(f"Failed to acquire database connection: {last_error}")

    def get_cursor(self) -> Cursor:
        """Get a cursor from a pooled connection."""
        # Return a mock cursor if we're in test mode
        if os.environ.get("MOCK_DB") == "1" or os.environ.get("USE_TEST_DB") == "1":
            from unittest.mock import MagicMock

            mock_cursor = MagicMock()
            logger.info("Returning mock database cursor for testing")
            return mock_cursor

        logger.debug("Getting database cursor")
        start_time = time.time()
        connection = self.connect()
        cursor = connection.cursor()
        elapsed_time = time.time() - start_time
        logger.debug(f"Database cursor acquired in {elapsed_time:.2f}s")
        return cursor

    def execute_with_retry(self, cursor: Cursor, query: str, params=None) -> None:
        """Execute query with retry logic."""
        last_error = None
        query_preview = query[:100] + "..." if len(query) > 100 else query
        logger.debug(f"Executing query with retry: {query_preview}")
        start_time = time.time()
        retry_connection = None

        for attempt in range(self.max_retries):
            try:
                cursor.execute(query, params)
                elapsed_time = time.time() - start_time
                logger.debug(f"Query executed successfully in {elapsed_time:.2f}s")
                return
            except (pymysql.OperationalError, pymysql.InternalError) as e:
                last_error = e
                elapsed_time = time.time() - start_time
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Query execution failed (attempt {attempt + 1}) after {elapsed_time:.2f}s: {e}. Retrying..."
                    )
                    try:
                        # Close the previous retry connection if we obtained one
                        if retry_connection is not None:
                            try:
                                retry_connection.close()
                            except Exception:
                                pass
                        # Get a new connection from the pool
                        retry_connection = self.connect()
                        cursor = retry_connection.cursor()
                    except Exception as conn_error:
                        logger.error(f"Failed to get new connection: {conn_error}")
                        raise

        # Clean up the last retry connection if we never succeeded
        if retry_connection is not None:
            try:
                retry_connection.close()
            except Exception:
                pass

        elapsed_time = time.time() - start_time
        if last_error:
            logger.error(f"Query execution failed after {self.max_retries} attempts and {elapsed_time:.2f}s: {last_error}")
            raise RuntimeError(f"Query execution failed after {self.max_retries} attempts: {last_error}")
        logger.error(f"Query execution failed after {self.max_retries} attempts and {elapsed_time:.2f}s")
        raise RuntimeError(f"Query execution failed after {self.max_retries} attempts")

    def close(self) -> None:
        """Close all connections in the pool."""
        if self.pool:
            try:
                self.pool.close_all()
                logger.info("All database connections closed")
            except Exception as e:
                logger.error(f"Error closing database connections: {e}")

    def check_connection(self, connection: Connection) -> Connection:
        """
        Check if a connection is alive and return a valid connection.

        Args:
            connection: The connection to check

        Returns:
            Connection: Either the original connection if valid, or a new connection if needed
        """
        try:
            # Try to ping the existing connection
            logger.debug("Checking database connection with ping")
            start_time = time.time()
            connection.ping(reconnect=True)
            elapsed_time = time.time() - start_time
            logger.debug(f"Connection ping successful in {elapsed_time:.2f}s")
            return connection
        except Exception as e:
            logger.warning(f"Connection check failed: {e}")
            try:
                # Return connection to pool if it's a PooledConnection
                if isinstance(connection, PooledConnection):
                    connection.close()

                # Get a fresh connection from the pool
                logger.info("Getting new connection after ping failure")
                new_connection = self.connect()
                logger.info("Successfully established new database connection")
                return new_connection
            except Exception as e:
                logger.error(f"Failed to reconnect to database: {e}")
                raise

    def ensure_connection(self, connection: Connection) -> Connection:
        """
        Ensure we have a valid database connection.

        Args:
            connection: The current connection object

        Returns:
            Connection: A valid database connection

        Raises:
            Exception: If unable to establish a valid connection
        """
        try:
            if not connection or not isinstance(connection, (Connection, PooledConnection)):
                return self.connect()
            return self.check_connection(connection)
        except Exception as e:
            logger.error(f"Failed to ensure database connection: {e}")
            raise


# Global instance
db_manager = DatabaseManager()
