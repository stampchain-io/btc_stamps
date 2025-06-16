"""
Tests for Market Data Service functionality.

This module tests the MarketDataService class and related database functions
for the Bitcoin Stamps Market Data Cache System.
"""

import json
import os

# Import the modules to test
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from index_core import database
from index_core.exceptions import DatabaseInsertError
from index_core.market_data_service import MarketDataService, market_data_service


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


class TestMarketDataBugFixes:
    """Test cases specifically for the SQL query construction and collection ID bugs fixed."""

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

    def test_update_src20_sql_query_construction(self):
        """Test that SQL query uses VALUES() function correctly for ON DUPLICATE KEY UPDATE."""
        tick = "TEST"
        data = {
            "floor_price_btc": Decimal("0.00001234"),
            "volume_24h_btc": Decimal("0.123"),
            "holder_count": 100,
            "primary_exchange": "test_exchange",
            "data_quality_score": 8.0,
        }

        with patch("index_core.caching.cache_manager.invalidate_cache_entry"):
            self.service.update_src20_market_data(tick, data)

        # Get the executed SQL query and parameters
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]
        sql_params = execute_call[0][1]

        # Verify VALUES() function is used in UPDATE clause
        assert "ON DUPLICATE KEY UPDATE" in sql_query
        assert "floor_price_btc = VALUES(floor_price_btc)" in sql_query
        assert "volume_24h_btc = VALUES(volume_24h_btc)" in sql_query
        assert "holder_count = VALUES(holder_count)" in sql_query
        assert "primary_exchange = VALUES(primary_exchange)" in sql_query
        assert "data_quality_score = VALUES(data_quality_score)" in sql_query
        assert "last_updated = NOW()" in sql_query

        # Verify parameter count matches placeholders
        # Should have: tick + 5 data fields = 6 parameters
        assert len(sql_params) == 6
        assert sql_params[0] == tick
        assert sql_params[1] == Decimal("0.00001234")
        assert sql_params[2] == Decimal("0.123")
        assert sql_params[3] == 100
        assert sql_params[4] == "test_exchange"
        assert sql_params[5] == 8.0

    def test_update_collection_hex_string_handling(self):
        """Test that collection IDs are properly handled as hex strings with UNHEX()."""
        collection_id = "EC179CF4CAA43C3A02C6C8B05F3DDAEE"
        data = {
            "floor_price_btc": Decimal("0.001"),
            "total_volume_btc": Decimal("10.5"),
            "unique_holders": 250,
        }

        with patch("index_core.caching.cache_manager.invalidate_cache_entry"):
            self.service.update_collection_market_data(collection_id, data)

        # Get the executed SQL query
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]
        sql_params = execute_call[0][1]

        # Verify UNHEX is used for collection_id
        assert "VALUES (UNHEX(%s)" in sql_query

        # Verify first parameter is the hex string
        assert sql_params[0] == collection_id
        assert isinstance(sql_params[0], str)
        assert len(sql_params[0]) == 32  # Hex string should be 32 chars

    def test_field_filtering_removes_invalid_fields(self):
        """Test that invalid fields are filtered out before SQL construction."""
        data = {
            "floor_price_btc": Decimal("0.001"),
            "invalid_field1": "should_be_ignored",
            "tick": "should_be_ignored",  # Primary key
            "cpid": "should_be_ignored",  # Primary key
            "collection_id": "should_be_ignored",  # Primary key
            "holder_count": 100,
            "last_updated": datetime.now(),  # Should be ignored - auto-set
            "created_at": datetime.now(),  # Should be ignored - auto-set
        }

        with patch("index_core.caching.cache_manager.invalidate_cache_entry"):
            self.service.update_src20_market_data("TEST", data)

        # Get the executed SQL query
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]
        sql_params = execute_call[0][1]

        # Verify invalid fields are not in query
        assert "invalid_field1" not in sql_query
        assert "tick" not in sql_query.split("(")[2]  # Not in column list

        # Verify only valid fields are in parameters
        # Should only have: tick + floor_price_btc + holder_count = 3 parameters
        assert len(sql_params) == 3
        assert sql_params[0] == "TEST"
        assert sql_params[1] == Decimal("0.001")
        assert sql_params[2] == 100

    def test_empty_data_logs_warning(self):
        """Test that empty data dict logs warning and returns without executing."""
        with patch("index_core.market_data_service.logger") as mock_logger:
            self.service.update_stamp_market_data("CPID", {})

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        assert "No valid fields provided" in mock_logger.warning.call_args[0][0]

        # Verify no SQL was executed
        self.mock_cursor.execute.assert_not_called()

    def test_get_collection_with_hex_query(self):
        """Test that get_collection_market_data uses HEX() in SELECT query."""
        collection_id = "EC179CF4CAA43C3A02C6C8B05F3DDAEE"

        # Mock cache miss to force DB query
        with patch("index_core.caching.cache_manager.get_cache_value", return_value=None):
            self.mock_cursor.fetchone.return_value = None  # No data found
            self.service.get_collection_market_data(collection_id)

        # Get the executed SQL query
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]
        sql_params = execute_call[0][1]

        # Verify HEX() is used in SELECT
        assert "HEX(collection_id) as collection_id" in sql_query

        # Verify UNHEX() is used in WHERE clause
        assert "WHERE collection_id = UNHEX(%s)" in sql_query

        # Verify parameter is hex string
        assert sql_params[0] == collection_id

    def test_decimal_precision_preserved(self):
        """Test that Decimal precision is preserved through update."""
        data = {
            "floor_price_btc": Decimal("0.123456789012345678"),  # High precision
            "volume_24h_btc": Decimal("1234567890.123456789"),  # Large number with decimals
        }

        with patch("index_core.caching.cache_manager.invalidate_cache_entry"):
            self.service.update_stamp_market_data("CPID", data)

        # Get the parameters passed to execute
        execute_call = self.mock_cursor.execute.call_args
        sql_params = execute_call[0][1]

        # Find the Decimal values in parameters
        decimal_values = [p for p in sql_params if isinstance(p, Decimal)]

        # Verify precision is preserved
        assert Decimal("0.123456789012345678") in decimal_values
        assert Decimal("1234567890.123456789") in decimal_values

    def test_null_values_handled_correctly(self):
        """Test that None/NULL values are properly handled."""
        data = {
            "floor_price_btc": None,
            "volume_24h_btc": None,
            "holder_count": 0,  # Zero should be allowed
            "data_quality_score": None,
        }

        with patch("index_core.caching.cache_manager.invalidate_cache_entry"):
            self.service.update_stamp_market_data("CPID", data)

        # Get the parameters
        execute_call = self.mock_cursor.execute.call_args
        sql_params = execute_call[0][1]

        # Count None values (excluding the CPID)
        none_count = sql_params[1:].count(None)
        assert none_count == 3  # Three None values

        # Verify zero is preserved
        assert 0 in sql_params


class TestOpenStampIntegration:
    """Test cases for OpenStamp API integration."""

    def setup_method(self):
        """Set up test fixtures."""
        # Mock environment for testing
        import os

        self.original_api_key = os.environ.get("OPENSTAMP_API_KEY")
        os.environ["OPENSTAMP_API_KEY"] = "test_api_key_for_testing"

    def teardown_method(self):
        """Clean up test fixtures."""
        import os

        if self.original_api_key:
            os.environ["OPENSTAMP_API_KEY"] = self.original_api_key
        else:
            os.environ.pop("OPENSTAMP_API_KEY", None)

    def test_openstamp_token_data_creation(self):
        """Test OpenStampTokenData object creation and conversion."""
        from decimal import Decimal

        from index_core.types import OpenStampTokenData

        # Sample data from OpenStamp API
        raw_data = {
            "tokenId": 1,
            "name": "KEVIN",
            "totalSupply": 690000000,
            "holdersCount": 2134,
            "price": "2.25",
            "amount24": "0",
            "volume24": "1000",
            "volume24Change": "0.1",
            "change24": "-0.2241",
            "change7d": "0.4516",
        }

        token_data = OpenStampTokenData(raw_data)

        # Test object properties
        assert token_data.token_id == 1
        assert token_data.name == "KEVIN"
        assert token_data.total_supply == 690000000
        assert token_data.holders_count == 2134
        assert token_data.price == Decimal("2.25")
        assert token_data.volume_24h == Decimal("1000")
        assert token_data.change_24h == Decimal("-0.2241")
        assert token_data.change_7d == Decimal("0.4516")

    def test_openstamp_token_data_to_market_data(self):
        """Test conversion to market data dictionary format."""
        from decimal import Decimal

        from index_core.types import OpenStampTokenData

        raw_data = {
            "tokenId": 2,
            "name": "STAMP",
            "totalSupply": 1000000000,
            "holdersCount": 13494,
            "price": "5.8",
            "amount24": "0",
            "volume24": "500",
            "volume24Change": "-1",
            "change24": "-0.1077",
            "change7d": "-0.42",
        }

        token_data = OpenStampTokenData(raw_data)
        market_data = token_data.to_market_data_dict()

        # Test required fields
        assert market_data["tick"] == "STAMP"
        assert market_data["price_btc"] == Decimal("5.8") / Decimal("100000000")  # Convert satoshis to BTC
        assert market_data["volume_24h_btc"] == Decimal("500") / Decimal("100000000")  # Convert satoshis to BTC
        assert market_data["holder_count"] == 13494
        assert market_data["circulating_supply"] == Decimal("1000000000")
        assert market_data["max_supply"] == Decimal("1000000000")

        # Test percentage conversions
        assert market_data["price_change_24h_percent"] == Decimal("-10.77")  # -0.1077 * 100
        assert market_data["price_change_7d_percent"] == Decimal("-42.0")  # -0.42 * 100

        # Test metadata
        assert market_data["primary_exchange"] == "openstamp"
        assert json.loads(market_data["exchange_sources"]) == ["openstamp"]
        assert market_data["data_quality_score"] == Decimal("8.0")
        assert market_data["confidence_level"] == Decimal("8.0")
        assert market_data["update_frequency_minutes"] == 5

    def test_openstamp_api_response_creation(self):
        """Test OpenStampApiResponse object creation."""
        from index_core.types import OpenStampApiResponse

        response_data = {
            "code": 200,
            "data": [
                {
                    "tokenId": 1,
                    "name": "KEVIN",
                    "totalSupply": 690000000,
                    "holdersCount": 2134,
                    "price": "2.25",
                    "amount24": "0",
                    "volume24": "0",
                    "volume24Change": "0",
                    "change24": "-0.2241",
                    "change7d": "0.4516",
                },
                {
                    "tokenId": 2,
                    "name": "STAMP",
                    "totalSupply": 1000000000,
                    "holdersCount": 13494,
                    "price": "5.8",
                    "amount24": "0",
                    "volume24": "0",
                    "volume24Change": "-1",
                    "change24": "-0.1077",
                    "change7d": "-0.42",
                },
            ],
        }

        api_response = OpenStampApiResponse(response_data)

        # Test response properties
        assert api_response.code == 200
        assert len(api_response.tokens) == 2

        # Test token retrieval
        kevin_token = api_response.get_token_by_name("KEVIN")
        assert kevin_token is not None
        assert kevin_token.name == "KEVIN"

        stamp_token = api_response.get_token_by_name("STAMP")
        assert stamp_token is not None
        assert stamp_token.name == "STAMP"

        # Test case insensitive retrieval
        kevin_lower = api_response.get_token_by_name("kevin")
        assert kevin_lower is not None
        assert kevin_lower.name == "KEVIN"

        # Test non-existent token
        missing_token = api_response.get_token_by_name("NONEXISTENT")
        assert missing_token is None

        # Test get all tickers
        all_tickers = api_response.get_all_tickers()
        assert "KEVIN" in all_tickers
        assert "STAMP" in all_tickers
        assert len(all_tickers) == 2

    @patch("index_core.openstamp_client.requests.Session.get")
    def test_openstamp_client_mock_response(self, mock_get):
        """Test OpenStamp client with mocked API response."""
        from unittest.mock import Mock

        from index_core.openstamp_client import OpenStampClient

        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 200,
            "data": [
                {
                    "tokenId": 1,
                    "name": "TEST",
                    "totalSupply": 1000000,
                    "holdersCount": 100,
                    "price": "1.5",
                    "amount24": "0",
                    "volume24": "100",
                    "volume24Change": "0",
                    "change24": "0.05",
                    "change7d": "0.1",
                }
            ],
        }
        mock_get.return_value = mock_response

        # Test client
        client = OpenStampClient(api_key="test_key")
        api_response = client.fetch_all_market_data()

        # Verify API call was made
        mock_get.assert_called_once()

        # Verify response processing
        assert len(api_response.tokens) == 1
        test_token = api_response.get_token_by_name("TEST")
        assert test_token is not None
        assert test_token.price == Decimal("1.5")

    def test_src20_worker_openstamp_integration(self):
        """Test SRC20Worker integration with OpenStamp (mocked)."""
        from unittest.mock import Mock, patch

        from index_core.src20_worker import SRC20Worker

        # Mock OpenStamp client
        with patch("index_core.src20_worker.get_openstamp_client") as mock_get_client:
            mock_client = Mock()
            mock_token_data = Mock()
            mock_token_data.to_market_data_dict.return_value = {
                "tick": "TEST",
                "price_btc": Decimal("1.5"),
                "volume_24h_btc": Decimal("100"),
                "holder_count": 100,
                "primary_exchange": "openstamp",
                "data_quality_score": Decimal("8.0"),
                "confidence_level": Decimal("8.0"),
            }
            mock_client.fetch_token_data.return_value = mock_token_data
            mock_get_client.return_value = mock_client

            # Test worker
            worker = SRC20Worker()
            result = worker._fetch_openstamp_data("TEST")

            # Verify result
            assert result is not None
            assert result["tick"] == "TEST"
            assert result["data_source"] == "openstamp"
            assert result["exchange_symbol"] == "TEST"


if __name__ == "__main__":
    pytest.main([__file__])
