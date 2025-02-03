import logging
import os
from typing import Any, Dict, List, Optional, Tuple, cast

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import Cursor, DictCursor

logger = logging.getLogger(__name__)


class ReparseDBManager:
    """Database manager that uses in-memory tables for reparse operations."""

    def __init__(self) -> None:
        self.connection: Optional[Connection] = None
        self._initialize_connection()

    def _get_connection_params(self) -> dict:
        """Get database connection parameters from environment."""
        return {
            "host": os.environ.get("RDS_HOSTNAME", "localhost"),
            "user": os.environ.get("RDS_USER") or os.environ.get("MYSQL_USER", "admin"),
            "password": os.environ.get("RDS_PASSWORD") or os.environ.get("MYSQL_PASSWORD", "password"),
            "database": os.environ.get("RDS_DATABASE", "btc_stamps"),  # Use existing database
            "port": int(os.environ.get("RDS_PORT", 3306)),
            "charset": "utf8mb4",
            "connect_timeout": 30,
            "read_timeout": 3600,
            "write_timeout": 3600,
        }

    def _create_minimal_schema(self, cursor: Cursor) -> None:
        """Create minimal schema needed for validation using temporary tables."""
        # Drop any existing temporary tables first
        cursor.execute("DROP TEMPORARY TABLE IF EXISTS _reparse_blocks")
        cursor.execute("DROP TEMPORARY TABLE IF EXISTS _reparse_stamps")
        cursor.execute("DROP TEMPORARY TABLE IF EXISTS _reparse_src20_ledger")

        # Create blocks table (only fields needed for hashing)
        cursor.execute(
            """
            CREATE TEMPORARY TABLE _reparse_blocks (
                block_index INTEGER NOT NULL,
                block_hash VARCHAR(64),
                messages_hash VARCHAR(64),
                txlist_hash VARCHAR(64),
                ledger_hash VARCHAR(64),
                PRIMARY KEY (block_index)
            ) ENGINE=MEMORY
        """
        )

        # Create minimal stamps table
        cursor.execute(
            """
            CREATE TEMPORARY TABLE _reparse_stamps (
                tx_index INTEGER NOT NULL,
                tx_hash VARCHAR(64),
                block_index INTEGER,
                PRIMARY KEY (tx_index)
            ) ENGINE=MEMORY
        """
        )

        # Create minimal src20_ledger table
        cursor.execute(
            """
            CREATE TEMPORARY TABLE _reparse_src20_ledger (
                block_index INTEGER NOT NULL,
                tx_hash VARCHAR(64),
                tick VARCHAR(10),
                PRIMARY KEY (block_index, tx_hash)
            ) ENGINE=MEMORY
        """
        )

        logger.info("Created temporary in-memory tables for validation")

    def _initialize_connection(self) -> None:
        """Initialize database connection with temporary in-memory tables."""
        try:
            params = self._get_connection_params()

            # Connect to existing database
            self.connection = pymysql.connect(**params)

            # Create temporary tables
            with self.connection.cursor() as cursor:
                self._create_minimal_schema(cursor)

            self.connection.commit()
            logger.info("Successfully initialized temporary tables")

        except Exception as e:
            logger.error(f"Failed to initialize temporary tables: {e}")
            if self.connection:
                self.connection.close()
                self.connection = None
            raise

    def connect(self) -> Connection:
        """Get the database connection, reconnecting if necessary."""
        try:
            if self.connection is None or not self.connection.open:
                self._initialize_connection()
            else:
                # Test connection and reconnect if needed
                try:
                    self.connection.ping()
                except Exception:
                    logger.debug("Connection lost, reconnecting...")
                    self._initialize_connection()

            # At this point, self.connection should never be None due to the checks above
            # and _initialize_connection() would raise an exception if it fails
            return cast(Connection, self.connection)
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise

    def close(self) -> None:
        """Close the database connection."""
        if self.connection and self.connection.open:
            try:
                # Drop temporary tables
                with self.connection.cursor() as cursor:
                    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _reparse_blocks")
                    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _reparse_stamps")
                    cursor.execute("DROP TEMPORARY TABLE IF EXISTS _reparse_src20_ledger")
                self.connection.commit()
                logger.info("Dropped temporary tables")
            except Exception as e:
                logger.warning(f"Error dropping temporary tables: {e}")
            finally:
                self.connection.close()
                self.connection = None

    def cursor(self, dictionary: bool = False) -> Cursor:
        """Get a cursor from the connection. Required to match DatabaseManager interface."""
        if not self.connection or not self.connection.open:
            self._initialize_connection()
        # After _initialize_connection(), self.connection should never be None
        conn = cast(Connection, self.connection)
        return conn.cursor(DictCursor if dictionary else None)

    def commit(self) -> None:
        """Commit the current transaction. Required to match DatabaseManager interface."""
        if self.connection and self.connection.open:
            self.connection.commit()

    def rollback(self) -> None:
        """Rollback the current transaction. Required to match DatabaseManager interface."""
        if self.connection and self.connection.open:
            self.connection.rollback()

    def begin(self) -> None:
        """Begin a new transaction. Required to match DatabaseManager interface."""
        if not self.connection or not self.connection.open:
            self._initialize_connection()
        # MySQL automatically begins a transaction, so we don't need to do anything here

    def execute(self, query: str, params: Optional[Any] = None) -> Tuple[List[Any], List[str]]:
        """Execute a query and return results with column names."""
        cursor = self.cursor()
        try:
            cursor.execute(query, params)
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                # Convert the tuple of tuples to a list of any
                result = list(cursor.fetchall())
                return result, columns
            return [], []
        finally:
            cursor.close()

    def executemany(self, query: str, params: List[Any]) -> None:
        """Execute a query with multiple parameter sets."""
        cursor = self.cursor()
        try:
            cursor.executemany(query, params)
        finally:
            cursor.close()

    def execute_values(self, query: str, params: List[Any], page_size: int = 1000) -> None:
        """Execute a query with multiple parameter sets in batches."""
        cursor = self.cursor()
        try:
            for i in range(0, len(params), page_size):
                batch = params[i : i + page_size]
                cursor.executemany(query, batch)
                if i % (page_size * 10) == 0:
                    self.commit()  # Commit every 10 batches
        finally:
            cursor.close()

    def fetchone(self, query: str, params: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """Fetch a single row as a dictionary."""
        cursor = self.cursor(dictionary=True)
        try:
            cursor.execute(query, params)
            result = cursor.fetchone()
            # Convert the tuple to a dictionary if it's not None
            if result is not None:
                return cast(Dict[str, Any], result)
            return None
        finally:
            cursor.close()

    def fetchall(self, query: str, params: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Fetch all rows as dictionaries."""
        cursor = self.cursor(dictionary=True)
        try:
            cursor.execute(query, params)
            # Convert the tuple of tuples to a list of dictionaries
            return cast(List[Dict[str, Any]], cursor.fetchall())
        finally:
            cursor.close()

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        cursor = self.cursor()
        try:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                AND table_name = %s
            """,
                (table_name,),
            )
            result = cursor.fetchone()
            # Safely access the first element of the tuple
            return cast(int, result[0]) > 0 if result else False
        finally:
            cursor.close()
