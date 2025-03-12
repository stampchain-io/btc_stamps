"""
Helper functions for testing the indexer.
"""

import os
import unittest.mock as mock
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional

# Update the import path to properly reference the backend module
from index_core.backend import Backend

# Set environment variables for testing
os.environ["USE_TEST_TX_HEX"] = "1"
os.environ["TESTING"] = "1"
os.environ["USE_TEST_DB"] = "1"
os.environ["MOCK_DB"] = "1"


def setup_test_environment():
    """
    Set up the test environment with all necessary environment variables.
    """
    # These environment variables tell the code to use test data
    os.environ["USE_TEST_TX_HEX"] = "1"
    os.environ["TESTING"] = "1"
    os.environ["USE_TEST_DB"] = "1"
    os.environ["MOCK_DB"] = "1"

    # Suppress RPC connection warnings
    os.environ["SUPPRESS_RPC_WARNINGS"] = "1"


# Add alias for backward compatibility
setup_test_env = setup_test_environment


@contextmanager
def mock_backend():
    """Context manager to mock the Backend class methods."""
    with mock.patch.object(Backend, "getrawtransaction") as mock_getrawtx:
        yield mock_getrawtx


def create_mock_tx_lookup(tx_data: Dict[str, str]) -> Callable:
    """
    Create a mock function for Backend.getrawtransaction that returns tx_hex from a dictionary.

    Args:
        tx_data: Dictionary mapping txids to their raw transaction hex

    Returns:
        Mock function that simulates Backend.getrawtransaction
    """

    def mock_getrawtransaction(*args, **kwargs):
        # Extract txid from args or kwargs
        txid = None
        if len(args) >= 2:  # self, txid, ...
            txid = args[1]
        elif "txid" in kwargs:
            txid = kwargs["txid"]
        elif len(args) == 1 and isinstance(args[0], str):
            # Handle case where it's called directly without self
            txid = args[0]

        if not txid:
            raise ValueError("No txid provided to mock_getrawtransaction")

        verbose = kwargs.get("verbose", False)

        if txid in tx_data:
            if verbose:
                # For verbose mode, return a dictionary structure similar to what the real method would return
                return {"hex": tx_data[txid], "txid": txid}
            else:
                # For non-verbose mode, just return the hex
                return tx_data[txid]
        else:
            # Simulate error for missing txids
            raise Exception(f"Transaction not found: {txid}")

    return mock_getrawtransaction


def load_test_tx_data(filename: str) -> Dict[str, str]:
    """
    Load test transaction data from a file.

    The file should contain lines with format: txid:hex

    Args:
        filename: Path to the file containing transaction data

    Returns:
        Dictionary mapping txids to their raw transaction hex
    """
    tx_data = {}
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    txid, hex_data = parts
                    tx_data[txid.strip()] = hex_data.strip()
    return tx_data


class MockDatabasePatcher:
    """
    A class that provides the same interface as a unittest.mock._patch object,
    but uses a context manager internally.
    """

    def __init__(self, mock_conn, cm):
        self.mock_conn = mock_conn
        self.cm = cm

    def start(self):
        # We don't actually start the patch here since it's already active
        # in the constructor, but we return the mock for compatibility
        return self.mock_conn

    def stop(self):
        # Clean up if needed - exit the context manager
        if self.cm:
            self.cm.__exit__(None, None, None)
            self.cm = None

    def __enter__(self):
        # Make this work as a context manager
        return self.mock_conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Clean up properly
        if self.cm:
            self.cm.__exit__(exc_type, exc_val, exc_tb)
            self.cm = None


def mock_database():
    """
    Mock the database connection for testing.

    This function can be used in two ways:
    1. As a context manager:
       with mock_database() as mock_db:
           # use mock_db

    2. With the start/stop pattern:
       patcher = mock_database()
       mock_db = patcher.start()
       # use mock_db
       patcher.stop()

    Returns:
        Either a context manager or a MockDatabasePatcher object
    """
    # Create a mock connection and cursor
    mock_conn = mock.MagicMock()
    mock_cursor = mock.MagicMock()

    # Configure the mock connection to return the mock cursor
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.execute = mock.MagicMock()
    mock_cursor.fetchall = mock.MagicMock(return_value=[])
    mock_cursor.fetchone = mock.MagicMock(return_value=None)

    # Set up a mock for the connect method that returns our mock connection
    connect_mock = mock.MagicMock(return_value=mock_conn)

    # Create and start the context manager
    cm = mock.patch("index_core.database.db_manager.connect", connect_mock)
    cm.__enter__()

    # For compatibility with older code that uses the start/stop pattern,
    # return a special patcher object that can be used with both approaches
    patcher = MockDatabasePatcher(mock_conn, cm)

    return patcher
