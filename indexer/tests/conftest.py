"""
Shared pytest fixtures for the test suite.
"""

import os
import threading
from decimal import Decimal

import pytest

# Ensure we're in test mode
os.environ["TESTING"] = "1"
os.environ["USE_TEST_DB"] = "1"
os.environ["MOCK_DB"] = "1"


@pytest.fixture(autouse=True)
def clear_caches():
    """Automatically clear all caches before each test to ensure test isolation."""
    # Import here to avoid circular imports
    from index_core.caching import cache_manager

    # Clear caches before the test
    cache_manager.clear_all()

    yield

    # Optionally clear caches after the test as well
    cache_manager.clear_all()


class MockDB:
    """Mock database connection for testing."""

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, *args, **kwargs):
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        """Mock close method."""
        pass


@pytest.fixture
def mock_db():
    """Fixture to provide a mock database connection."""
    return MockDB()


@pytest.fixture
def thread_lock():
    """Fixture to provide a thread lock for concurrent operations."""
    return threading.Lock()


@pytest.fixture
def sample_src20_deploy():
    """Fixture to provide a sample SRC-20 deploy transaction."""
    return {
        "p": "src-20",
        "op": "DEPLOY",  # Note: Using uppercase to match processor
        "tick": "TEST",
        "lim": "1000",
        "max": "21000000",
        "dec": 18,
        "tx_hash": "test_hash",
        "block_index": 865002,
        "source": "test_address",
        "destination": "test_address",
        "creator": "test_address",
        "block_time": 1712745958,
        "tx_index": 769794,
    }


@pytest.fixture
def sample_src20_mint():
    """Fixture to provide a sample SRC-20 mint transaction."""
    return {
        "p": "src-20",
        "op": "MINT",  # Note: Using uppercase to match processor
        "tick": "TEST",
        "amt": "100",
        "tx_hash": "test_hash_mint",
        "block_index": 865003,
        "source": "test_address",
        "destination": "test_address",
        "creator": "test_address",
        "block_time": 1712745959,
        "tx_index": 769795,
    }


@pytest.fixture
def sample_src20_transfer():
    """Fixture to provide a sample SRC-20 transfer transaction."""
    return {
        "p": "src-20",
        "op": "TRANSFER",  # Note: Using uppercase to match processor
        "tick": "TEST",
        "amt": "50",
        "tx_hash": "test_hash_transfer",
        "block_index": 865004,
        "source": "test_address",
        "destination": "recipient_address",
        "creator": "test_address",
        "block_time": 1712745960,
        "tx_index": 769796,
    }
