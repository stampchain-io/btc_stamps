"""
Tests for Market Data Source Tracking

This module tests the market_data_sources table functionality that tracks
individual API source data for transparency and reliability analysis.
"""

import os
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from index_core import database
from index_core.exceptions import DatabaseInsertError


class TestMarketDataSourceTracking:
    """Test cases for market data source tracking functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_db = Mock()
        self.mock_cursor = Mock()

        # Setup mock database connection with context manager support
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = self.mock_cursor
        cursor_context.__exit__.return_value = None
        self.mock_db.cursor.return_value = cursor_context

    def test_insert_market_data_source_success(self):
        """Test successful insertion of market data source record."""
        source_data = {
            "asset_type": "src20",
            "asset_id": "STAMP",
            "source_name": "kucoin",
            "price_btc": Decimal("0.00000004"),
            "volume_24h_btc": Decimal("8.12"),
            "holder_count": None,
            "market_cap_btc": None,
            "source_confidence": Decimal("9.5"),
            "api_response_time_ms": 245,
            "last_updated": datetime.now(),
            "success_rate_24h": Decimal("100.0"),
            "consecutive_failures": 0,
            "last_success": datetime.now(),
            "last_failure": None,
        }

        database.insert_market_data_source(self.mock_db, source_data)

        # Verify execute and commit were called
        self.mock_cursor.execute.assert_called_once()
        self.mock_db.commit.assert_called_once()

        # Verify SQL structure
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]
        sql_params = execute_call[0][1]

        # Check that all required fields are in the query
        assert "asset_type" in sql_query
        assert "asset_id" in sql_query
        assert "source_name" in sql_query
        assert "price_btc" in sql_query
        assert "source_confidence" in sql_query

        # Check parameter values
        assert "src20" in sql_params
        assert "STAMP" in sql_params
        assert "kucoin" in sql_params
        assert Decimal("9.5") in sql_params

    def test_insert_market_data_source_openstamp_data(self):
        """Test insertion of OpenStamp source data."""
        source_data = {
            "asset_type": "src20",
            "asset_id": "UTXO",
            "source_name": "openstamp",
            "price_btc": Decimal("0.0000075"),
            "volume_24h_btc": Decimal("0.0005"),
            "holder_count": 1798,
            "market_cap_btc": Decimal("0.0075"),
            "source_confidence": Decimal("8.5"),
            "api_response_time_ms": 180,
            "last_updated": datetime.now(),
            "success_rate_24h": Decimal("98.5"),
            "consecutive_failures": 0,
            "last_success": datetime.now(),
            "last_failure": None,
        }

        database.insert_market_data_source(self.mock_db, source_data)

        self.mock_cursor.execute.assert_called_once()
        self.mock_db.commit.assert_called_once()

    def test_insert_market_data_source_missing_required_fields(self):
        """Test insertion with missing required fields."""
        source_data = {
            "asset_type": "src20",
            # Missing asset_id and source_name
            "price_btc": Decimal("0.001"),
        }

        with pytest.raises(DatabaseInsertError):
            database.insert_market_data_source(self.mock_db, source_data)

    def test_insert_market_data_source_database_error(self):
        """Test handling of database errors during insertion."""
        source_data = {
            "asset_type": "src20",
            "asset_id": "TEST",
            "source_name": "test_source",
            "source_confidence": Decimal("5.0"),
        }

        # Mock database error
        self.mock_cursor.execute.side_effect = Exception("Database error")

        with pytest.raises(DatabaseInsertError):
            database.insert_market_data_source(self.mock_db, source_data)

        # Verify rollback was called
        self.mock_db.rollback.assert_called_once()

    def test_get_market_data_sources_by_asset_type(self):
        """Test getting market data sources filtered by asset type."""
        expected_data = [
            (
                1,
                "src20",
                "STAMP",
                "kucoin",
                Decimal("0.00000004"),
                Decimal("8.12"),
                None,
                None,
                Decimal("9.5"),
                245,
                Decimal("100.0"),
                datetime.now(),
                None,
                0,
                datetime.now(),
                24,
                datetime.now(),
            ),
            (
                2,
                "src20",
                "STAMP",
                "openstamp",
                Decimal("0.000000058"),
                Decimal("0"),
                13494,
                None,
                Decimal("8.0"),
                180,
                Decimal("98.5"),
                datetime.now(),
                None,
                0,
                datetime.now(),
                24,
                datetime.now(),
            ),
        ]
        self.mock_cursor.fetchall.return_value = expected_data

        result = database.get_market_data_sources(self.mock_db, asset_type="src20")

        assert result == expected_data

        # Verify SQL query includes asset_type filter
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]
        sql_params = execute_call[0][1]

        assert "WHERE asset_type = %s" in sql_query
        assert "src20" in sql_params

    def test_get_market_data_sources_by_asset_id(self):
        """Test getting market data sources for specific asset."""
        expected_data = [
            (
                1,
                "src20",
                "STAMP",
                "kucoin",
                Decimal("0.00000004"),
                Decimal("8.12"),
                None,
                None,
                Decimal("9.5"),
                245,
                Decimal("100.0"),
                datetime.now(),
                None,
                0,
                datetime.now(),
                24,
                datetime.now(),
            ),
        ]
        self.mock_cursor.fetchall.return_value = expected_data

        result = database.get_market_data_sources(self.mock_db, asset_type="src20", asset_id="STAMP")

        assert result == expected_data

        # Verify SQL query includes both filters
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]
        sql_params = execute_call[0][1]

        assert "WHERE asset_type = %s AND asset_id = %s" in sql_query
        assert "src20" in sql_params
        assert "STAMP" in sql_params

    def test_get_market_data_sources_all_sources(self):
        """Test getting all market data sources without filters."""
        expected_data = [
            (
                1,
                "src20",
                "STAMP",
                "kucoin",
                Decimal("0.00000004"),
                Decimal("8.12"),
                None,
                None,
                Decimal("9.5"),
                245,
                Decimal("100.0"),
                datetime.now(),
                None,
                0,
                datetime.now(),
                24,
                datetime.now(),
            ),
            (
                2,
                "src20",
                "UTXO",
                "openstamp",
                Decimal("0.0000075"),
                Decimal("0.0005"),
                1798,
                None,
                Decimal("8.0"),
                180,
                Decimal("98.5"),
                datetime.now(),
                None,
                0,
                datetime.now(),
                24,
                datetime.now(),
            ),
            (
                3,
                "stamp",
                "A123456789",
                "counterparty",
                Decimal("0.001"),
                Decimal("0.05"),
                None,
                Decimal("100"),
                Decimal("9.0"),
                150,
                Decimal("99.0"),
                datetime.now(),
                None,
                0,
                datetime.now(),
                24,
                datetime.now(),
            ),
        ]
        self.mock_cursor.fetchall.return_value = expected_data

        result = database.get_market_data_sources(self.mock_db)

        assert result == expected_data
        assert len(result) == 3

        # Verify no WHERE clause when no filters
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]

        assert "WHERE" not in sql_query

    def test_market_data_source_upsert_behavior(self):
        """Test ON DUPLICATE KEY UPDATE behavior for source records."""
        source_data = {
            "asset_type": "src20",
            "asset_id": "STAMP",
            "source_name": "kucoin",
            "price_btc": Decimal("0.00000005"),  # Updated price
            "volume_24h_btc": Decimal("10.0"),  # Updated volume
            "source_confidence": Decimal("9.0"),
            "api_response_time_ms": 200,
            "success_rate_24h": Decimal("99.5"),
            "consecutive_failures": 0,
        }

        database.insert_market_data_source(self.mock_db, source_data)

        # Verify SQL uses ON DUPLICATE KEY UPDATE
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]

        assert "ON DUPLICATE KEY UPDATE" in sql_query
        assert "price_btc = VALUES(price_btc)" in sql_query
        assert "volume_24h_btc = VALUES(volume_24h_btc)" in sql_query
        assert "source_confidence = VALUES(source_confidence)" in sql_query

    def test_source_confidence_tracking(self):
        """Test tracking of source confidence over time."""
        # Test high confidence source
        high_confidence_data = {
            "asset_type": "src20",
            "asset_id": "STAMP",
            "source_name": "kucoin",
            "price_btc": Decimal("0.00000004"),
            "volume_24h_btc": Decimal("8.12"),
            "source_confidence": Decimal("9.5"),
            "success_rate_24h": Decimal("100.0"),
            "consecutive_failures": 0,
        }

        database.insert_market_data_source(self.mock_db, high_confidence_data)

        # Test medium confidence source
        medium_confidence_data = {
            "asset_type": "src20",
            "asset_id": "UTXO",
            "source_name": "openstamp",
            "price_btc": Decimal("0.0000075"),
            "source_confidence": Decimal("7.5"),
            "success_rate_24h": Decimal("95.0"),
            "consecutive_failures": 1,
        }

        database.insert_market_data_source(self.mock_db, medium_confidence_data)

        # Verify both were processed
        assert self.mock_cursor.execute.call_count == 2

    def test_api_response_time_tracking(self):
        """Test tracking of API response times."""
        fast_response_data = {
            "asset_type": "src20",
            "asset_id": "STAMP",
            "source_name": "kucoin",
            "api_response_time_ms": 150,  # Fast response
            "source_confidence": Decimal("9.0"),
        }

        slow_response_data = {
            "asset_type": "src20",
            "asset_id": "UTXO",
            "source_name": "openstamp",
            "api_response_time_ms": 2500,  # Slow response
            "source_confidence": Decimal("6.0"),  # Lower confidence due to slowness
        }

        database.insert_market_data_source(self.mock_db, fast_response_data)
        database.insert_market_data_source(self.mock_db, slow_response_data)

        # Verify response times are properly recorded
        execute_calls = self.mock_cursor.execute.call_args_list

        # Check first call (fast response)
        first_call_params = execute_calls[0][0][1]
        assert 150 in first_call_params

        # Check second call (slow response)
        second_call_params = execute_calls[1][0][1]
        assert 2500 in second_call_params

    def test_failure_tracking(self):
        """Test tracking of API failures."""
        failure_data = {
            "asset_type": "src20",
            "asset_id": "FAILED_TOKEN",
            "source_name": "test_api",
            "price_btc": None,  # No data due to failure
            "volume_24h_btc": None,
            "source_confidence": Decimal("2.0"),  # Low confidence due to failure
            "success_rate_24h": Decimal("75.0"),  # Reduced success rate
            "consecutive_failures": 3,  # Multiple failures
            "last_failure": datetime.now(),
            "last_success": None,  # No recent success
        }

        database.insert_market_data_source(self.mock_db, failure_data)

        # Verify failure tracking fields are included
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]
        sql_params = execute_call[0][1]

        assert "consecutive_failures" in sql_query
        assert "success_rate_24h" in sql_query
        assert "last_failure" in sql_query
        assert 3 in sql_params  # consecutive_failures value
        assert Decimal("75.0") in sql_params  # success_rate_24h value

    def test_null_value_handling_in_sources(self):
        """Test proper handling of NULL values in source data."""
        partial_data = {
            "asset_type": "src20",
            "asset_id": "PARTIAL_TOKEN",
            "source_name": "partial_api",
            "price_btc": None,  # No price data
            "volume_24h_btc": Decimal("1.0"),  # Has volume
            "holder_count": None,  # No holder data
            "market_cap_btc": None,  # No market cap
            "source_confidence": Decimal("5.0"),
        }

        database.insert_market_data_source(self.mock_db, partial_data)

        # Verify NULL values are handled properly
        execute_call = self.mock_cursor.execute.call_args
        sql_params = execute_call[0][1]

        # Count None values in parameters
        none_count = sql_params.count(None)
        assert none_count >= 3  # Should have at least 3 None values

        # Verify non-None values are present
        assert Decimal("1.0") in sql_params  # volume_24h_btc
        assert Decimal("5.0") in sql_params  # source_confidence


class TestSourceDataIntegration:
    """Integration tests for source data tracking with SRC20Worker."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_db = Mock()
        self.mock_cursor = Mock()

        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = self.mock_cursor
        cursor_context.__exit__.return_value = None
        self.mock_db.cursor.return_value = cursor_context

    def test_source_data_storage_integration(self):
        """Test integration between SRC20Worker and source data storage."""
        from index_core.src20_worker import SRC20Worker

        worker = SRC20Worker()

        # Mock source data
        source_data = {
            "kucoin": {
                "tick": "STAMP",
                "price_btc": Decimal("0.00000004"),
                "volume_24h_btc": Decimal("8.12"),
                "data_quality_score": Decimal("9.0"),
            },
            "openstamp": {
                "tick": "STAMP",
                "price_btc": Decimal("0.000000058"),
                "holder_count": 13494,
                "data_quality_score": Decimal("8.0"),
            },
        }

        with patch("index_core.database.insert_market_data_source") as mock_insert:
            # Mock database connection
            with patch.object(worker.processor.db_manager, "get_long_running_connection") as mock_get_db:
                mock_get_db.return_value = self.mock_db

                worker._store_source_data("STAMP", source_data)

            # Verify insert was called for each source
            assert mock_insert.call_count == 2

            # Verify call structure
            insert_calls = mock_insert.call_args_list

            # First call should be for kucoin
            kucoin_call = insert_calls[0]
            kucoin_db = kucoin_call[0][0]
            kucoin_record = kucoin_call[0][1]

            assert kucoin_db == self.mock_db
            assert kucoin_record["asset_type"] == "src20"
            assert kucoin_record["asset_id"] == "STAMP"
            assert kucoin_record["source_name"] == "kucoin"
            assert kucoin_record["price_btc"] == Decimal("0.00000004")

            # Second call should be for openstamp
            openstamp_call = insert_calls[1]
            openstamp_record = openstamp_call[0][1]

            assert openstamp_record["source_name"] == "openstamp"
            assert openstamp_record["holder_count"] == 13494

    def test_confidence_calculation_integration(self):
        """Test confidence calculation integration with source storage."""
        from index_core.src20_worker import SRC20Worker

        worker = SRC20Worker()

        # Test confidence calculation for different source types
        kucoin_data = {
            "price_btc": Decimal("0.00000004"),
            "volume_24h_btc": Decimal("8.12"),
        }

        openstamp_data = {
            "price_btc": Decimal("0.000000058"),
            "holder_count": 13494,
        }

        kucoin_confidence = worker._calculate_source_confidence("kucoin", kucoin_data)
        openstamp_confidence = worker._calculate_source_confidence("openstamp", openstamp_data)

        # KuCoin should have higher confidence due to trading data
        assert kucoin_confidence >= openstamp_confidence
        assert kucoin_confidence <= 10.0
        assert openstamp_confidence >= 0.0


if __name__ == "__main__":
    pytest.main([__file__])
