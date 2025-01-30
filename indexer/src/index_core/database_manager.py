"""Database connection management and pooling for PyMySQL."""

import logging
import os
import queue
import threading
import time
from typing import Optional, Dict

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import Cursor

logger = logging.getLogger(__name__)


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

            # Verify the connection is still alive
            try:
                connection.ping(reconnect=True)
            except:
                # Connection is dead, remove it and create a new one
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
            # Verify the connection is still usable
            connection.ping(reconnect=True)
            self._pool.put(connection, timeout=self.timeout)
        except:
            # Connection is dead, remove it
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
                except:
                    pass
                del self._active_connections[conn_id]

        # Create a new connection to replace the removed one if we're below min_connections
        if self.get_pool_size() < self.min_connections:
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
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                self._remove_connection(conn)
            except queue.Empty:
                break

        with self._lock:
            for conn in list(self._active_connections.values()):
                self._remove_connection(conn)


class DatabaseManager:
    def __init__(self):
        self.max_retries = 3
        self.retry_delay = 2
        self.connect_timeout = 10
        self.read_timeout = 30
        self.write_timeout = 30
        self.pool = None
        self._initialize_pool()

    def _initialize_pool(self):
        """Initialize the connection pool with parameters from environment."""
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
        return {
            "host": os.environ.get("RDS_HOSTNAME", "db"),
            "user": os.environ.get("RDS_USER"),
            "password": os.environ.get("RDS_PASSWORD"),
            "database": os.environ.get("RDS_DATABASE", "btc_stamps"),
            "port": int(os.environ.get("RDS_PORT", 3306)),
            "connect_timeout": self.connect_timeout,
            "read_timeout": self.read_timeout,
            "write_timeout": self.write_timeout,
            "charset": "utf8mb4",
            "autocommit": False,
            "client_flag": pymysql.constants.CLIENT.MULTI_STATEMENTS,
            "init_command": "SET SESSION wait_timeout=28800",
        }

    def connect(self) -> Connection:
        """Get a connection from the pool with retries."""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                connection = self.pool.get_connection()
                if connection:
                    logger.info("Database connection acquired from pool")
                    return connection
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    logger.warning(f"Database connection attempt {attempt + 1} failed. Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)

        logger.error(f"Failed to acquire database connection after {self.max_retries} attempts")
        raise last_error

    def get_cursor(self) -> Cursor:
        """Get a cursor from a pooled connection."""
        connection = self.connect()
        return connection.cursor()

    def execute_with_retry(self, cursor: Cursor, query: str, params=None) -> None:
        """Execute query with retry logic."""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                cursor.execute(query, params)
                return
            except (pymysql.OperationalError, pymysql.InternalError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(f"Query execution failed (attempt {attempt + 1}). Retrying...")
                    try:
                        # Get a new connection from the pool
                        connection = self.connect()
                        cursor = connection.cursor()
                    except Exception as conn_error:
                        logger.error(f"Failed to get new connection: {conn_error}")
                        raise

        raise last_error

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
            connection.ping(reconnect=True)
            return connection
        except Exception as e:
            logger.warning(f"Connection check failed: {e}")
            try:
                # Return connection to pool if it's a PooledConnection
                if isinstance(connection, PooledConnection):
                    connection.close()

                # Get a fresh connection from the pool
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
