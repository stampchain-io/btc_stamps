"""
Database fixtures for standardized testing across the codebase.

This module provides reusable database fixtures that can be used to:
1. Mock database connections consistently
2. Provide pre-populated test data
3. Simplify test setup and teardown
4. Improve test isolation
"""

from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, Mock

import pytest


@pytest.fixture
def mock_db_manager():
    """
    Provides a mock DatabaseManager with common behaviors.

    Returns a DatabaseManager mock that:
    - Has connect() method returning a mock connection
    - Has get_cursor() method returning a mock cursor
    - Supports context manager protocol
    """
    manager = Mock()
    connection = Mock()
    cursor = Mock()

    # Setup cursor context manager
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor
    cursor_context.__exit__.return_value = None

    # Setup connection
    connection.cursor.return_value = cursor_context
    connection.close = Mock()
    connection.commit = Mock()
    connection.rollback = Mock()

    # Setup manager
    manager.connect.return_value = connection
    manager.get_cursor.return_value = cursor
    manager.get_long_running_connection.return_value = connection

    return manager


@pytest.fixture
def mock_db_connection(mock_db_manager):
    """
    Provides a mock database connection.

    Returns a connection mock with:
    - cursor() method returning a context manager
    - commit(), rollback(), close() methods
    """
    return mock_db_manager.connect()


@pytest.fixture
def mock_cursor(mock_db_connection):
    """
    Provides a mock database cursor.

    Returns a cursor mock with:
    - execute() method
    - fetchone(), fetchall() methods
    - rowcount property
    """
    with mock_db_connection.cursor() as cursor:
        cursor.rowcount = 0
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        cursor.execute.return_value = None
        yield cursor


@pytest.fixture
def populated_stamp_db(mock_cursor):
    """
    Provides a mock database cursor with pre-populated stamp data.

    Sets up mock responses for common stamp queries.
    """
    # Sample stamp data
    sample_stamps = [
        {
            "stamp_hash": "abc123",
            "cpid": "A123456789",
            "stamp": "STAMPY",
            "block_index": 820000,
            "tx_hash": "def456",
            "tx_index": 100,
            "stamp_mimetype": "image/png",
            "is_btc_stamp": 1,
            "is_valid": 1,
        },
        {
            "stamp_hash": "xyz789",
            "cpid": "A987654321",
            "stamp": "RARESTAMP",
            "block_index": 820001,
            "tx_hash": "ghi012",
            "tx_index": 101,
            "stamp_mimetype": "image/gif",
            "is_btc_stamp": 1,
            "is_valid": 1,
        },
    ]

    # Configure fetchall to return sample data
    mock_cursor.fetchall.return_value = sample_stamps
    mock_cursor.fetchone.return_value = sample_stamps[0] if sample_stamps else None
    mock_cursor.rowcount = len(sample_stamps)

    return mock_cursor


@pytest.fixture
def populated_src20_db(mock_cursor):
    """
    Provides a mock database cursor with pre-populated SRC-20 data.

    Sets up mock responses for common SRC-20 queries.
    """
    # Sample SRC-20 data
    sample_src20 = [
        {
            "id": 1,
            "tx_hash": "abc123",
            "block_index": 820000,
            "tick": "STAMP",
            "op": "DEPLOY",
            "amt": Decimal("1000000"),
            "lim": Decimal("1000"),
            "max": Decimal("21000000"),
            "dec": 18,
            "creator": "1AddressCreator",
            "valid": 1,
            "status": "valid",
        },
        {
            "id": 2,
            "tx_hash": "def456",
            "block_index": 820001,
            "tick": "STAMP",
            "op": "MINT",
            "amt": Decimal("1000"),
            "p": "1AddressMinter",
            "valid": 1,
            "status": "valid",
        },
    ]

    mock_cursor.fetchall.return_value = sample_src20
    mock_cursor.fetchone.return_value = sample_src20[0] if sample_src20 else None
    mock_cursor.rowcount = len(sample_src20)

    return mock_cursor


@pytest.fixture
def mock_transaction_response():
    """
    Provides mock transaction data for testing.

    Returns a dictionary mimicking transaction response structure.
    """
    return {
        "tx_hash": "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2",
        "tx_index": 2500,
        "block_index": 820000,
        "source": "1SourceAddress",
        "destination": "1DestAddress",
        "btc_amount": 546,
        "fee": 1000,
        "data": b"sample_data",
        "supported": 1,
    }


@pytest.fixture
def mock_block_response():
    """
    Provides mock block data for testing.

    Returns a dictionary mimicking block response structure.
    """
    return {
        "block_index": 820000,
        "block_hash": "00000000000000000000ba232574c32b4f0cd023e133c05125310625626d6571",
        "block_time": int(datetime.now().timestamp()),
        "previous_block_hash": "00000000000000000000000000000000000000000000000000000000000000",
        "difficulty": 123456789,
        "ledger_hash": "abcdef123456",
        "txlist_hash": "fedcba654321",
        "messages_hash": "aabbccddee",
    }


@pytest.fixture
def db_error_scenarios():
    """
    Provides common database error scenarios for testing error handling.

    Returns a list of tuples (exception_class, error_message).
    """
    return [
        (Exception, "Database connection failed"),
        (TimeoutError, "Query timeout exceeded"),
        (ValueError, "Invalid query parameters"),
        (KeyError, "Missing required column"),
    ]


@pytest.fixture
def mock_db_with_errors(mock_cursor):
    """
    Provides a mock cursor that simulates database errors.

    Useful for testing error handling paths.
    """
    mock_cursor.execute.side_effect = Exception("Database error")
    mock_cursor.fetchone.side_effect = Exception("Fetch error")
    mock_cursor.fetchall.side_effect = Exception("Fetch error")
    return mock_cursor


# Context managers for specific test scenarios


@contextmanager
def mock_database_transaction(mock_db_connection):
    """
    Context manager for testing database transactions.

    Usage:
        with mock_database_transaction(mock_db) as (db, cursor):
            # Test transaction logic
            pass
    """
    cursor = mock_db_connection.cursor().__enter__()
    try:
        yield mock_db_connection, cursor
        mock_db_connection.commit()
    except Exception:
        mock_db_connection.rollback()
        raise
    finally:
        cursor.__exit__(None, None, None)


@pytest.fixture
def assert_database_called():
    """
    Helper fixture for asserting database calls were made correctly.

    Returns a function that can verify database interactions.
    """

    def _assert(cursor, expected_query=None, expected_params=None, times=1):
        assert cursor.execute.call_count == times
        if expected_query:
            actual_query = cursor.execute.call_args[0][0]
            assert expected_query in actual_query
        if expected_params:
            actual_params = cursor.execute.call_args[0][1]
            assert actual_params == expected_params

    return _assert
