"""
Tests for Market Data Service functionality.

This module tests the MarketDataService class and related database functions
for the Bitcoin Stamps Market Data Cache System.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import the modules to test
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from index_core.market_data_service import MarketDataService, market_data_service
from index_core import database
from index_core.exceptions import DatabaseInsertError


class TestMarketDataService:
    """Test cases for MarketDataService class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_db_manager = Mock()
        self.mock_db = Mock()
        self.mock_cursor = Mock()

        # Setup mock database connection with context manager support
        self.mock_db_manager.connect.return_value = self.mock_db
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = self.mock_cursor
        cursor_context.__exit__.return_value = None
        self.mock_db.cursor.return_value = cursor_context

        # Create service instance with mocked dependencies
        self.service = MarketDataService(self.mock_db_manager)

    def test_service_initialization(self):
        """Test that the service initializes correctly."""
        assert self.service.db_manager == self.mock_db_manager

    def test_get_stamp_market_data_cache_hit(self):
        """Test getting stamp market data with cache hit."""
        # Mock cache hit
        cached_data = {"cpid": "A123456789", "floor_price_btc": Decimal("0.001"), "holder_count": 100}

        with patch("index_core.caching.cache_manager.get_cache_value", return_value=cached_data):
            result = self.service.get_stamp_market_data("A123456789", use_cache=True)

        assert result == cached_data
        # Verify database was not called
        self.mock_db_manager.connect.assert_not_called()

    def test_get_stamp_market_data_cache_miss(self):
        """Test getting stamp market data with cache miss."""
        # Mock cache miss and database response
        self.mock_cursor.fetchone.return_value = (
            "A123456789",
            Decimal("0.001"),
            Decimal("0.0015"),
            5,
            2,
            7,
            100,
            95,
            Decimal("15.5"),
            Decimal("8.2"),
            Decimal("0.05"),
            Decimal("0.35"),
            Decimal("1.2"),
            Decimal("5.8"),
            "openstamp",
            "openstamp,stampscan",
            Decimal("9.5"),
            Decimal("8.8"),
            datetime.now(),
            865000,
            865000,
            datetime.now(),
            60,
            datetime.now(),
        )

        with patch("index_core.caching.cache_manager.get_cache_value", return_value=None):
            with patch("index_core.caching.cache_manager.set_cache_value") as mock_set:
                result = self.service.get_stamp_market_data("A123456789", use_cache=True)

        # Verify database was called
        self.mock_db_manager.connect.assert_called_once()
        # Verify cache was set
        mock_set.assert_called_once()
        # Verify result structure
        assert result["cpid"] == "A123456789"
        assert result["floor_price_btc"] == Decimal("0.001")

    def test_get_stamp_market_data_not_found(self):
        """Test getting stamp market data when not found in database."""
        # Mock cache miss and no database result
        self.mock_cursor.fetchone.return_value = None

        with patch("index_core.caching.cache_manager.get_cache_value", return_value=None):
            result = self.service.get_stamp_market_data("NONEXISTENT", use_cache=True)

        assert result is None

    def test_update_stamp_market_data(self):
        """Test updating stamp market data."""
        market_data = {"floor_price_btc": Decimal("0.002"), "holder_count": 105, "volume_24h_btc": Decimal("0.1")}

        with patch("index_core.caching.cache_manager.invalidate_cache_entry") as mock_delete:
            self.service.update_stamp_market_data("A123456789", market_data)

        # Verify cache was invalidated
        mock_delete.assert_called_once()
        # Verify database operations were called
        self.mock_cursor.execute.assert_called()
        self.mock_db.commit.assert_called()

    def test_get_src20_market_data(self):
        """Test getting SRC-20 market data."""
        # Mock database response
        self.mock_cursor.fetchone.return_value = (
            "PEPE",
            Decimal("0.0001"),
            Decimal("0.05"),
            Decimal("0.00008"),
            Decimal("1000"),
            Decimal("50000"),
            Decimal("10"),
            Decimal("70"),
            Decimal("300"),
            Decimal("1500"),
            Decimal("5.2"),
            Decimal("-2.1"),
            Decimal("15.8"),
            5000,
            Decimal("500000"),
            Decimal("1000000"),
            "kucoin",
            "kucoin,openstamp",
            Decimal("9.0"),
            Decimal("8.5"),
            datetime.now(),
            datetime.now(),
            30,
            datetime.now(),
        )

        with patch("index_core.caching.cache_manager.get_cache_value", return_value=None):
            result = self.service.get_src20_market_data("PEPE", use_cache=True)

        assert result["tick"] == "PEPE"
        assert result["price_btc"] == Decimal("0.0001")

    def test_get_stamp_holders(self):
        """Test getting stamp holders."""
        # Mock database response
        self.mock_cursor.fetchall.return_value = [
            ("A123456789", "address1", Decimal("100"), Decimal("50.0"), 1, "counterparty", datetime.now(), 865000),
            ("A123456789", "address2", Decimal("50"), Decimal("25.0"), 2, "counterparty", datetime.now(), 865000),
        ]

        result = self.service.get_stamp_holders("A123456789", limit=10)

        assert len(result) == 2
        assert result[0]["address"] == "address1"
        assert result[0]["quantity"] == Decimal("100")

    def test_get_trending_stamps_via_database(self):
        """Test getting trending stamps via database function."""
        # Mock database response
        self.mock_cursor.fetchall.return_value = [
            (
                "A123456789",
                1,
                "creator1",
                Decimal("0.001"),
                100,
                Decimal("0.05"),
                Decimal("0.35"),
                Decimal("8.2"),
                Decimal("9.5"),
            ),
            (
                "B987654321",
                2,
                "creator2",
                Decimal("0.002"),
                80,
                Decimal("0.03"),
                Decimal("0.25"),
                Decimal("7.8"),
                Decimal("8.9"),
            ),
        ]

        # Test via database function since service doesn't have this method yet
        result = database.get_trending_stamps(self.mock_db, limit=20)

        assert len(result) == 2
        assert result[0][0] == "A123456789"  # cpid is first element in tuple
        assert result[0][8] == Decimal("9.5")  # trending_score is 9th element

    def test_service_methods_exist(self):
        """Test that the service has the expected methods."""
        assert hasattr(self.service, "get_stamp_market_data")
        assert hasattr(self.service, "get_src20_market_data")
        assert hasattr(self.service, "get_collection_market_data")
        assert hasattr(self.service, "update_stamp_market_data")
        assert hasattr(self.service, "update_src20_market_data")
        assert hasattr(self.service, "get_stamp_holders")

    def test_global_service_instance(self):
        """Test that the global service instance is properly initialized."""
        # The global instance should be available
        assert market_data_service is not None
        assert isinstance(market_data_service, MarketDataService)


class TestMarketDataDatabaseFunctions:
    """Test cases for market data database functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_db = Mock()
        self.mock_cursor = Mock()

        # Setup mock database connection with context manager support
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = self.mock_cursor
        cursor_context.__exit__.return_value = None
        self.mock_db.cursor.return_value = cursor_context

    def test_get_stamp_market_data_raw(self):
        """Test getting raw stamp market data from database."""
        # Mock database response
        expected_data = (
            "A123456789",
            Decimal("0.001"),
            Decimal("0.0015"),
            5,
            2,
            7,
            100,
            95,
            Decimal("15.5"),
            Decimal("8.2"),
            Decimal("0.05"),
            Decimal("0.35"),
            Decimal("1.2"),
            Decimal("5.8"),
            "openstamp",
            "openstamp,stampscan",
            Decimal("9.5"),
            Decimal("8.8"),
            datetime.now(),
            865000,
            865000,
            datetime.now(),
            60,
            datetime.now(),
        )
        self.mock_cursor.fetchone.return_value = expected_data

        result = database.get_stamp_market_data_raw(self.mock_db, "A123456789")

        assert result == expected_data
        self.mock_cursor.execute.assert_called_once()

    def test_get_stamp_market_data_raw_not_found(self):
        """Test getting raw stamp market data when not found."""
        self.mock_cursor.fetchone.return_value = None

        result = database.get_stamp_market_data_raw(self.mock_db, "NONEXISTENT")

        assert result is None

    def test_insert_stamp_market_data_success(self):
        """Test successful insertion of stamp market data."""
        market_data = {
            "cpid": "A123456789",
            "floor_price_btc": Decimal("0.001"),
            "holder_count": 100,
            "volume_24h_btc": Decimal("0.05"),
            "data_quality_score": Decimal("9.5"),
        }

        database.insert_stamp_market_data(self.mock_db, market_data)

        # Verify execute and commit were called
        self.mock_cursor.execute.assert_called_once()
        self.mock_db.commit.assert_called_once()

    def test_insert_stamp_market_data_missing_cpid(self):
        """Test insertion with missing required cpid field."""
        market_data = {"floor_price_btc": Decimal("0.001"), "holder_count": 100}

        with pytest.raises(DatabaseInsertError, match="Failed to insert stamp market data"):
            database.insert_stamp_market_data(self.mock_db, market_data)

    def test_insert_stamp_market_data_database_error(self):
        """Test handling of database errors during insertion."""
        market_data = {"cpid": "A123456789", "floor_price_btc": Decimal("0.001")}

        # Mock database error
        self.mock_cursor.execute.side_effect = Exception("Database error")

        with pytest.raises(DatabaseInsertError):
            database.insert_stamp_market_data(self.mock_db, market_data)

        # Verify rollback was called
        self.mock_db.rollback.assert_called_once()

    def test_get_src20_market_data_raw(self):
        """Test getting raw SRC-20 market data from database."""
        expected_data = (
            "PEPE",
            Decimal("0.0001"),
            Decimal("0.05"),
            Decimal("0.00008"),
            Decimal("1000"),
            Decimal("50000"),
            Decimal("10"),
            Decimal("70"),
            Decimal("300"),
            Decimal("1500"),
            Decimal("5.2"),
            Decimal("-2.1"),
            Decimal("15.8"),
            5000,
            Decimal("500000"),
            Decimal("1000000"),
            "kucoin",
            "kucoin,openstamp",
            Decimal("9.0"),
            Decimal("8.5"),
            datetime.now(),
            datetime.now(),
            30,
            datetime.now(),
        )
        self.mock_cursor.fetchone.return_value = expected_data

        result = database.get_src20_market_data_raw(self.mock_db, "PEPE")

        assert result == expected_data

    def test_insert_src20_market_data_success(self):
        """Test successful insertion of SRC-20 market data."""
        market_data = {"tick": "PEPE", "price_btc": Decimal("0.0001"), "holder_count": 5000, "market_cap_btc": Decimal("1000")}

        database.insert_src20_market_data(self.mock_db, market_data)

        self.mock_cursor.execute.assert_called_once()
        self.mock_db.commit.assert_called_once()

    def test_get_stamp_holders_raw(self):
        """Test getting raw stamp holder data."""
        expected_data = [
            ("A123456789", "address1", Decimal("100"), Decimal("50.0"), 1, "counterparty", datetime.now(), 865000),
            ("A123456789", "address2", Decimal("50"), Decimal("25.0"), 2, "counterparty", datetime.now(), 865000),
        ]
        self.mock_cursor.fetchall.return_value = expected_data

        result = database.get_stamp_holders_raw(self.mock_db, "A123456789", limit=10)

        assert result == expected_data
        self.mock_cursor.execute.assert_called_once()

    def test_insert_stamp_holder_data_success(self):
        """Test successful insertion of stamp holder data."""
        holder_data = {
            "cpid": "A123456789",
            "address": "address1",
            "quantity": Decimal("100"),
            "percentage": Decimal("50.0"),
            "rank_position": 1,
        }

        database.insert_stamp_holder_data(self.mock_db, holder_data)

        self.mock_cursor.execute.assert_called_once()
        self.mock_db.commit.assert_called_once()

    def test_insert_stamp_holder_data_missing_required_fields(self):
        """Test insertion with missing required fields."""
        holder_data = {"quantity": Decimal("100")}

        with pytest.raises(DatabaseInsertError, match="Failed to insert holder data"):
            database.insert_stamp_holder_data(self.mock_db, holder_data)

    def test_get_market_data_sources(self):
        """Test getting market data sources."""
        expected_data = [
            (
                1,
                "stamp",
                "A123456789",
                "openstamp",
                Decimal("0.001"),
                Decimal("0.05"),
                100,
                Decimal("100"),
                Decimal("9.5"),
                200,
                Decimal("99.5"),
                datetime.now(),
                None,
                0,
                datetime.now(),
                24,
                datetime.now(),
            ),
        ]
        self.mock_cursor.fetchall.return_value = expected_data

        result = database.get_market_data_sources(self.mock_db, asset_type="stamp", asset_id="A123456789")

        assert result == expected_data

    def test_insert_market_data_source_success(self):
        """Test successful insertion of market data source."""
        source_data = {
            "asset_type": "stamp",
            "asset_id": "A123456789",
            "source_name": "openstamp",
            "price_btc": Decimal("0.001"),
            "source_confidence": Decimal("9.5"),
        }

        database.insert_market_data_source(self.mock_db, source_data)

        self.mock_cursor.execute.assert_called_once()
        self.mock_db.commit.assert_called_once()

    def test_get_trending_stamps(self):
        """Test getting trending stamps from view."""
        expected_data = [
            (
                "A123456789",
                1,
                "creator1",
                Decimal("0.001"),
                100,
                Decimal("0.05"),
                Decimal("0.35"),
                Decimal("8.2"),
                Decimal("9.5"),
            ),
        ]
        self.mock_cursor.fetchall.return_value = expected_data

        result = database.get_trending_stamps(self.mock_db, limit=20)

        assert result == expected_data

    def test_get_stamp_market_overview(self):
        """Test getting stamp market overview from view."""
        expected_data = [
            (
                "A123456789",
                1,
                "creator1",
                "https://example.com/stamp1.png",
                "image/png",
                Decimal("0.001"),
                100,
                Decimal("0.05"),
                Decimal("9.5"),
                datetime.now(),
                "fresh",
            ),
        ]
        self.mock_cursor.fetchall.return_value = expected_data

        result = database.get_stamp_market_overview(self.mock_db, limit=100)

        assert result == expected_data


class TestMarketDataIntegration:
    """Integration tests for market data functionality."""

    def test_service_database_integration(self):
        """Test integration between service and database functions."""
        # This would be an integration test that uses a real test database
        # For now, we'll mock the integration points

        mock_db_manager = Mock()
        mock_db = Mock()
        mock_cursor = Mock()

        mock_db_manager.connect.return_value = mock_db
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = mock_cursor
        cursor_context.__exit__.return_value = None
        mock_db.cursor.return_value = cursor_context

        service = MarketDataService(mock_db_manager)

        # Mock database response for stamp market data
        mock_cursor.fetchone.return_value = (
            "A123456789",
            Decimal("0.001"),
            Decimal("0.0015"),
            5,
            2,
            7,
            100,
            95,
            Decimal("15.5"),
            Decimal("8.2"),
            Decimal("0.05"),
            Decimal("0.35"),
            Decimal("1.2"),
            Decimal("5.8"),
            "openstamp",
            "openstamp,stampscan",
            Decimal("9.5"),
            Decimal("8.8"),
            datetime.now(),
            865000,
            865000,
            datetime.now(),
            60,
            datetime.now(),
        )

        with patch("index_core.caching.cache_manager.get_cache_value", return_value=None):
            result = service.get_stamp_market_data("A123456789", use_cache=False)

        assert result is not None
        assert result["cpid"] == "A123456789"
        assert result["floor_price_btc"] == Decimal("0.001")


if __name__ == "__main__":
    pytest.main([__file__])
