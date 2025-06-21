"""
Fixtures for SRC20Worker tests.

These fixtures provide reusable mock data and configurations for testing
the SRC20Worker's KuCoin API integration and data processing.
"""

from decimal import Decimal
from unittest.mock import MagicMock, Mock

import pytest


@pytest.fixture
def mock_btc_usdt_response():
    """Mock successful BTC/USDT API response from KuCoin."""
    return {"bestBid": "105000.50", "bestAsk": "105001.50"}


@pytest.fixture
def mock_stamp_ticker_response():
    """Mock STAMP ticker response with 24h stats."""
    return {
        "last": "0.0000125",  # Price high enough to stay above MIN_PRICE
        "vol": "650000.50",
        "changeRate": "-0.0454",
        "high": "0.0000130",
        "low": "0.0000120",
    }


@pytest.fixture
def mock_stamp_orderbook_response():
    """Mock STAMP orderbook response."""
    return {"bestBid": "0.0000124", "bestAsk": "0.0000126"}


@pytest.fixture
def kucoin_api_side_effect(mock_btc_usdt_response, mock_stamp_ticker_response, mock_stamp_orderbook_response):
    """
    Returns a side effect function for mocking _kucoin_api_call.

    This handles different endpoints and symbols to simulate the full API.
    """

    def api_side_effect(endpoint, params):
        symbol = params.get("symbol", "")

        if "BTC-USDT" in symbol:
            return mock_btc_usdt_response
        elif "STAMP-USDT" in symbol:
            if "stats" in endpoint:
                return mock_stamp_ticker_response
            elif "orderbook" in endpoint:
                return mock_stamp_orderbook_response
        return None

    return api_side_effect


@pytest.fixture
def mock_kucoin_api_success(kucoin_api_side_effect):
    """Mock successful KuCoin API calls with proper side effects."""
    mock = Mock()
    mock.side_effect = kucoin_api_side_effect
    return mock


@pytest.fixture
def mock_kucoin_api_failure():
    """Mock failed KuCoin API calls."""
    mock = Mock()
    mock.return_value = None
    return mock


@pytest.fixture
def mock_kucoin_api_timeout():
    """Mock KuCoin API timeout."""
    mock = Mock()
    mock.side_effect = Exception("Timeout")
    return mock


@pytest.fixture
def mock_stampscan_api():
    """Mock StampScan API."""
    mock = Mock()
    mock.return_value = None  # Default to no data
    return mock


@pytest.fixture
def mock_openstamp_api():
    """Mock OpenStamp API."""
    mock = Mock()
    mock.return_value = None  # Default to no data
    return mock


@pytest.fixture
def mock_reliability_tracker():
    """Mock reliability tracker for API sources."""
    tracker = MagicMock()
    tracker.record_success = Mock()
    tracker.record_failure = Mock()
    tracker.get_reliability_score = Mock(return_value=0.95)
    return tracker


@pytest.fixture
def src20_worker():
    """Create a fresh SRC20Worker instance for testing."""
    from index_core.src20_worker import SRC20Worker

    return SRC20Worker()


@pytest.fixture
def expected_market_data_fields():
    """List of required fields in market data response."""
    return [
        "tick",
        "price_btc",
        "volume_24h_btc",
        "price_change_24h_percent",
        "data_quality_score",
        "confidence_level",
        "update_frequency_minutes",
    ]


@pytest.fixture
def stamp_exchange_config():
    """Expected STAMP configuration in exchange mappings."""
    return {"kucoin": "STAMP-USDT", "symbol": "STAMP", "base_currency": "USDT"}


# Helper fixtures for complex test scenarios


@pytest.fixture
def all_apis_fail_setup(mock_kucoin_api_timeout, mock_stampscan_api, mock_openstamp_api, mock_reliability_tracker):
    """Setup where all API sources fail."""
    return {
        "kucoin": mock_kucoin_api_timeout,
        "stampscan": mock_stampscan_api,
        "openstamp": mock_openstamp_api,
        "tracker": mock_reliability_tracker,
    }


@pytest.fixture
def btc_rate_cache_setup(mock_btc_usdt_response):
    """Setup for testing BTC rate caching."""
    mock_api = Mock()
    mock_api.return_value = mock_btc_usdt_response
    return mock_api


@pytest.fixture
def assert_market_data_valid():
    """Helper to validate market data response structure."""

    def _assert(result, expected_tick="STAMP"):
        assert result is not None
        assert result["tick"] == expected_tick

        # Check numeric fields
        price_btc = float(result["price_btc"])
        volume_btc = float(result["volume_24h_btc"])
        confidence = float(result["confidence_level"])

        assert price_btc > 0
        assert volume_btc > 0
        assert 0.0 <= confidence <= 10.0

        return True

    return _assert
