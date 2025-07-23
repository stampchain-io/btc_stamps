"""
Unit tests for StampActivityCalculator

These tests use mocked database connections and do not require external API access.
They focus on the logic of activity level calculations and update intervals.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from index_core.activity_calculator import ActivityLevel, StampActivityCalculator


class TestStampActivityCalculator:
    """Unit tests for StampActivityCalculator with mocked dependencies"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        # Test runs, any cleanup can go here
        yield
        # Cleanup after test if needed

    def test_activity_level_enum_values(self):
        """Test that ActivityLevel enum has correct values"""
        assert ActivityLevel.HOT.value == "HOT"
        assert ActivityLevel.WARM.value == "WARM"
        assert ActivityLevel.COOL.value == "COOL"
        assert ActivityLevel.DORMANT.value == "DORMANT"
        assert ActivityLevel.COLD.value == "COLD"

    def test_update_intervals_defined(self):
        """Test that all activity levels have defined update intervals"""
        intervals = StampActivityCalculator.UPDATE_INTERVALS

        assert ActivityLevel.HOT in intervals
        assert ActivityLevel.WARM in intervals
        assert ActivityLevel.COOL in intervals
        assert ActivityLevel.DORMANT in intervals
        assert ActivityLevel.COLD in intervals

        # Verify intervals are sensible (in minutes)
        assert intervals[ActivityLevel.HOT] == 60  # 1 hour
        assert intervals[ActivityLevel.WARM] == 360  # 6 hours
        assert intervals[ActivityLevel.COOL] == 1440  # 24 hours
        assert intervals[ActivityLevel.DORMANT] == 2880  # 48 hours
        assert intervals[ActivityLevel.COLD] == 10080  # 7 days

    def test_calculate_activity_level_hot(self):
        """Test calculation of HOT activity level"""
        now = datetime.now().timestamp()
        recent_sale = int(now - 3600)  # 1 hour ago

        level = StampActivityCalculator.calculate_activity_level(last_sale_time=recent_sale, has_active_dispensers=False)

        assert level == ActivityLevel.HOT

    def test_calculate_activity_level_warm(self):
        """Test calculation of WARM activity level"""
        now = datetime.now().timestamp()
        recent_sale = int(now - 2 * 24 * 3600)  # 2 days ago

        level = StampActivityCalculator.calculate_activity_level(last_sale_time=recent_sale, has_active_dispensers=False)

        assert level == ActivityLevel.WARM

    def test_calculate_activity_level_cool(self):
        """Test calculation of COOL activity level"""
        now = datetime.now().timestamp()
        old_sale = int(now - 15 * 24 * 3600)  # 15 days ago

        level = StampActivityCalculator.calculate_activity_level(last_sale_time=old_sale, has_active_dispensers=False)

        assert level == ActivityLevel.COOL

    def test_calculate_activity_level_dormant(self):
        """Test calculation of DORMANT activity level"""
        now = datetime.now().timestamp()
        very_old_sale = int(now - 60 * 24 * 3600)  # 60 days ago

        level = StampActivityCalculator.calculate_activity_level(
            last_sale_time=very_old_sale, has_active_dispensers=True  # Has dispensers
        )

        assert level == ActivityLevel.DORMANT

    def test_calculate_activity_level_cold(self):
        """Test calculation of COLD activity level"""
        now = datetime.now().timestamp()
        very_old_sale = int(now - 60 * 24 * 3600)  # 60 days ago

        level = StampActivityCalculator.calculate_activity_level(
            last_sale_time=very_old_sale, has_active_dispensers=False  # No dispensers
        )

        assert level == ActivityLevel.COLD

    def test_calculate_activity_level_no_sales(self):
        """Test calculation when no sales exist"""
        # No sales, no dispensers = COLD
        level = StampActivityCalculator.calculate_activity_level(last_sale_time=None, has_active_dispensers=False)
        assert level == ActivityLevel.COLD

        # No sales, but has dispensers = DORMANT
        level = StampActivityCalculator.calculate_activity_level(last_sale_time=None, has_active_dispensers=True)
        assert level == ActivityLevel.DORMANT

    def test_should_update_market_data_never_updated(self):
        """Test that stamps never updated should always be updated"""
        result = StampActivityCalculator.should_update_market_data(ActivityLevel.COLD, last_updated=None)
        assert result is True

    def test_should_update_market_data_hot_stamp(self):
        """Test update logic for HOT stamps"""
        now = datetime.now()

        # 30 minutes ago - should not update yet (interval is 60 min)
        recent_update = now - timedelta(minutes=30)
        result = StampActivityCalculator.should_update_market_data(ActivityLevel.HOT, last_updated=recent_update)
        assert result is False

        # 90 minutes ago - should update (interval is 60 min)
        old_update = now - timedelta(minutes=90)
        result = StampActivityCalculator.should_update_market_data(ActivityLevel.HOT, last_updated=old_update)
        assert result is True

    def test_should_update_market_data_cold_stamp(self):
        """Test update logic for COLD stamps"""
        now = datetime.now()

        # 3 days ago - should not update yet (interval is 7 days)
        recent_update = now - timedelta(days=3)
        result = StampActivityCalculator.should_update_market_data(ActivityLevel.COLD, last_updated=recent_update)
        assert result is False

        # 8 days ago - should update (interval is 7 days)
        old_update = now - timedelta(days=8)
        result = StampActivityCalculator.should_update_market_data(ActivityLevel.COLD, last_updated=old_update)
        assert result is True

    def test_update_activity_on_sale(self, mock_db_connection, mock_cursor):
        """Test updating activity level when sale occurs"""
        # Configure mock
        mock_cursor.rowcount = 1
        # Mock the SELECT query result (sales data)
        mock_cursor.fetchone.return_value = (
            900000,  # last_sale_block
            1000000,  # volume_24h_sats
            5000000,  # volume_7d_sats
            10000000,  # volume_30d_sats
            20000000,  # total_volume_sats
            50000,  # recent_price_sats
            "tx123",  # last_sale_tx
            "buyer123",  # last_buyer
            "seller123",  # last_seller
            100000,  # last_sale_amount
            "dispenser123",  # last_dispenser_tx
        )

        StampActivityCalculator.update_activity_on_sale("A123456789", mock_db_connection)

        # Verify both SQL calls were made
        assert mock_cursor.execute.call_count == 2

        # First call should be SELECT
        first_call = mock_cursor.execute.call_args_list[0][0][0]
        assert "SELECT" in first_call
        assert "FROM stamp_sales_history" in first_call

        # Second call should be UPDATE
        second_call = mock_cursor.execute.call_args_list[1][0][0]
        assert "UPDATE stamp_market_data" in second_call
        assert "activity_level = 'HOT'" in second_call
        assert "last_activity_time = UNIX_TIMESTAMP()" in second_call

    def test_update_activity_on_dispenser_change_add(self, mock_db_connection, mock_cursor):
        """Test updating activity level when dispensers are added"""
        StampActivityCalculator.update_activity_on_dispenser_change("A123456789", True, mock_db_connection)

        # Verify SQL was called
        mock_cursor.execute.assert_called_once()
        sql_call = mock_cursor.execute.call_args[0][0]
        assert "UPDATE stamp_market_data" in sql_call
        assert "WHEN activity_level = 'COLD' THEN 'DORMANT'" in sql_call

    def test_update_activity_on_dispenser_change_remove(self, mock_db_connection, mock_cursor):
        """Test updating activity level when dispensers are removed"""
        StampActivityCalculator.update_activity_on_dispenser_change("A123456789", False, mock_db_connection)

        # Verify SQL was called twice (once for the parameterized query)
        assert mock_cursor.execute.call_count == 1
        sql_call = mock_cursor.execute.call_args[0][0]
        assert "UPDATE stamp_market_data" in sql_call
        assert "WHEN activity_level = 'DORMANT'" in sql_call

    def test_get_stamps_needing_update(self, mock_db_connection, mock_cursor):
        """Test getting stamps that need updates"""
        # Mock database results
        mock_cursor.fetchall.return_value = [
            ("A123456789", "12345", "HOT", None),
            ("A987654321", "67890", "WARM", None),
            ("A555444333", "11111", "COLD", None),
        ]

        results = StampActivityCalculator.get_stamps_needing_update(mock_db_connection, limit=1000)

        # Verify results
        assert len(results) == 3
        assert "A123456789" in results
        assert results["A123456789"] == ("12345", ActivityLevel.HOT)
        assert results["A987654321"] == ("67890", ActivityLevel.WARM)
        assert results["A555444333"] == ("11111", ActivityLevel.COLD)

        # Verify SQL was called
        mock_cursor.execute.assert_called_once()
        sql_call = mock_cursor.execute.call_args[0][0]
        assert "SELECT" in sql_call
        assert "activity_level" in sql_call
        assert "ORDER BY" in sql_call

    def test_get_stamps_needing_update_empty(self, mock_db_connection, mock_cursor):
        """Test getting stamps when none need updates"""
        mock_cursor.fetchall.return_value = []

        results = StampActivityCalculator.get_stamps_needing_update(mock_db_connection)

        assert len(results) == 0
        assert isinstance(results, dict)

    def test_log_activity_stats(self, mock_db_connection, mock_cursor):
        """Test logging activity level statistics"""
        # Mock database results
        mock_cursor.fetchall.return_value = [
            ("HOT", 50, 1.5, 150.0),
            ("WARM", 200, 0.8, 120.0),
            ("COOL", 500, 0.3, 80.0),
            ("DORMANT", 1000, 0.1, 60.0),
            ("COLD", 40000, 0.0, 30.0),
        ]

        # Should not raise any exceptions
        StampActivityCalculator.log_activity_stats(mock_db_connection)

        # Verify SQL was called
        mock_cursor.execute.assert_called_once()
        sql_call = mock_cursor.execute.call_args[0][0]
        assert "SELECT" in sql_call
        assert "activity_level" in sql_call
        assert "GROUP BY activity_level" in sql_call

    def test_error_handling_in_db_operations(self, mock_db_connection, mock_cursor):
        """Test that database errors are handled gracefully"""
        # Make database operations raise an exception
        mock_cursor.execute.side_effect = Exception("Database error")

        # These should not raise exceptions, but handle errors gracefully
        StampActivityCalculator.update_activity_on_sale("A123456789", mock_db_connection)
        StampActivityCalculator.update_activity_on_dispenser_change("A123456789", True, mock_db_connection)

        results = StampActivityCalculator.get_stamps_needing_update(mock_db_connection)
        assert results == {}  # Should return empty dict on error

        # This should also not raise
        StampActivityCalculator.log_activity_stats(mock_db_connection)
