"""
Shared pytest fixtures for the test suite.
"""

import os
import threading

import pytest

# Ensure we're in test mode
os.environ["TESTING"] = "1"
os.environ["USE_TEST_DB"] = "1"
os.environ["MOCK_DB"] = "1"

# Import database fixtures to make them available globally
from .fixtures.database_fixtures import (  # noqa: F401
    assert_database_called,
    db_error_scenarios,
    mock_block_response,
    mock_cursor,
    mock_db_connection,
    mock_db_manager,
    mock_db_with_errors,
    mock_transaction_response,
    populated_src20_db,
    populated_stamp_db,
)

# Import SRC20 integration test fixtures to make them available
# These imports look unused but are actually used by pytest's fixture system  # noqa: F401
from .fixtures.src20_test_fixtures import (  # noqa: F401
    cached_transactions,
    invalid_transactions,
    transaction_by_hash,
    transaction_hashes_data,
    valid_transactions,
)

# Import SRC20 worker fixtures
from .fixtures.src20_worker_fixtures import (  # noqa: F401
    all_apis_fail_setup,
    assert_market_data_valid,
    btc_rate_cache_setup,
    expected_market_data_fields,
    kucoin_api_side_effect,
    mock_btc_usdt_response,
    mock_kucoin_api_failure,
    mock_kucoin_api_success,
    mock_kucoin_api_timeout,
    mock_openstamp_api,
    mock_reliability_tracker,
    mock_stamp_orderbook_response,
    mock_stamp_ticker_response,
    mock_stampscan_api,
    src20_worker,
    stamp_exchange_config,
)


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
