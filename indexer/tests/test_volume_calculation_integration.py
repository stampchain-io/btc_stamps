"""
Integration test for volume calculation from sales history.
This test verifies the complete flow from sales data to volume metrics.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from index_core.database_manager import DatabaseManager
from index_core.market_data_service import MarketDataService
from index_core.sales_history_processor import SalesHistoryProcessor
from index_core.stamp_worker import StampWorker


class TestVolumeCalculationIntegration:
    """Test the complete volume calculation flow."""

    @pytest.fixture
    def test_cpid(self):
        """Test CPID to use."""
        return "A12345678901234567890"

    @pytest.fixture
    def test_sales_data(self, test_cpid):
        """Generate test sales data with various timestamps."""
        now = datetime.now()
        return [
            # Sale from 1 hour ago
            {
                "tx_hash": "tx1",
                "block_index": 900000,
                "block_time": int((now - timedelta(hours=1)).timestamp()),
                "cpid": test_cpid,
                "btc_amount": 50000,  # 0.0005 BTC
                "unit_price_sats": 50000,
                "quantity": 1,
            },
            # Sale from 3 days ago
            {
                "tx_hash": "tx2",
                "block_index": 899500,
                "block_time": int((now - timedelta(days=3)).timestamp()),
                "cpid": test_cpid,
                "btc_amount": 100000,  # 0.001 BTC
                "unit_price_sats": 100000,
                "quantity": 1,
            },
            # Sale from 10 days ago
            {
                "tx_hash": "tx3",
                "block_index": 899000,
                "block_time": int((now - timedelta(days=10)).timestamp()),
                "cpid": test_cpid,
                "btc_amount": 200000,  # 0.002 BTC
                "unit_price_sats": 200000,
                "quantity": 1,
            },
            # Sale from 40 days ago (outside 30d window)
            {
                "tx_hash": "tx4",
                "block_index": 898000,
                "block_time": int((now - timedelta(days=40)).timestamp()),
                "cpid": test_cpid,
                "btc_amount": 300000,  # 0.003 BTC
                "unit_price_sats": 300000,
                "quantity": 1,
            },
        ]

    def test_sales_history_to_volume_calculation(self, mock_db_manager, mock_cursor, test_cpid, test_sales_data):
        """Test that sales history data correctly flows to volume calculations."""
        # Setup mock database responses
        mock_cursor.fetchone.side_effect = [
            # Response for 24h volume query
            (50000, 1, 50000, 50000, test_sales_data[0]["block_time"]),
            # Response for 7d volume query
            (150000, 2, 100000, 50000, test_sales_data[0]["block_time"]),
            # Response for 30d volume query
            (350000, 3, 200000, 50000, test_sales_data[0]["block_time"]),
            # Response for recent sales query
            None,  # No results for simplicity
        ]

        # Create processor instance
        with patch("index_core.sales_history_processor.DatabaseManager"), patch(
            "index_core.sales_history_processor.Backend"
        ), patch("index_core.sales_history_processor.OpenStampClient"):
            processor = SalesHistoryProcessor()
            processor.db_manager = mock_db_manager  # Replace with mocked db_manager

        # Mock the cursor to return expected results (values are already in BTC in the database)
        mock_cursor.fetchone.side_effect = [
            (0.0005,),  # 24h volume query result in BTC
            (0.0015,),  # 7d volume query result in BTC
            (0.0035,),  # 30d volume query result in BTC
        ]

        # Test 24h volume calculation
        volume_24h = processor.calculate_volume_from_history(test_cpid, hours=24)
        assert volume_24h == 0.0005  # Already in BTC

        # Test 7d volume calculation
        volume_7d = processor.calculate_volume_from_history(test_cpid, hours=24 * 7)
        assert volume_7d == 0.0015  # Already in BTC

        # Test 30d volume calculation
        volume_30d = processor.calculate_volume_from_history(test_cpid, hours=24 * 30)
        assert volume_30d == 0.0035  # Already in BTC

    def test_stamp_worker_volume_integration(self, mock_db_manager, mock_cursor, test_cpid):
        """Test that stamp worker correctly retrieves and formats volume data."""
        # Mock the sales history processor responses
        with patch("index_core.stamp_worker.sales_history_processor") as mock_processor:
            # Setup mock responses - calculate_volume_from_history returns floats
            mock_processor.calculate_volume_from_history.side_effect = [
                0.0005,  # 24h volume
                0.0015,  # 7d volume
                0.0035,  # 30d volume
                0.0065,  # total volume
            ]
            mock_processor.get_recent_sales.return_value = []

            # Create stamp worker
            worker = StampWorker()

            # Calculate volume metrics
            volume_metrics = worker._calculate_volume_metrics_from_history(test_cpid)

            # Verify the results
            assert volume_metrics["volume_24h_btc"] == 0.0005
            assert volume_metrics["volume_7d_btc"] == 0.0015
            assert volume_metrics["volume_30d_btc"] == 0.0035
            assert volume_metrics["recent_dispenses_count"] == 0  # TODO: Not implemented yet
            assert volume_metrics["total_dispenses_count"] == 0  # TODO: Not implemented yet

    def test_market_data_service_update(self, mock_db_manager, mock_cursor, test_cpid):
        """Test that market data service correctly stores volume data."""
        # Setup mock cursor for the UPDATE/INSERT
        mock_cursor.rowcount = 1

        # Create market data service
        service = MarketDataService(db_manager=mock_db_manager)

        # Test data to update
        market_data = {
            "volume_24h_btc": Decimal("0.0005"),
            "volume_7d_btc": Decimal("0.0015"),
            "volume_30d_btc": Decimal("0.0035"),
            "floor_price_btc": Decimal("0.00025"),
            "holder_count": 10,
        }

        # Update market data
        service.update_stamp_market_data(test_cpid, market_data)

        # Verify the SQL was executed
        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0]
        sql_query = call_args[0]
        sql_params = call_args[1]

        # Check that volume fields are in the query
        assert "volume_24h_btc" in sql_query
        assert "volume_7d_btc" in sql_query
        assert "volume_30d_btc" in sql_query

        # Check that values are passed correctly
        assert Decimal("0.0005") in sql_params
        assert Decimal("0.0015") in sql_params
        assert Decimal("0.0035") in sql_params

    def test_zero_volume_handling(self, mock_db_manager, mock_cursor, test_cpid):
        """Test that zero volumes are handled correctly."""
        # Setup mock for no sales
        mock_cursor.fetchone.return_value = (None, 0, None, None, None)

        with patch("index_core.sales_history_processor.DatabaseManager"), patch(
            "index_core.sales_history_processor.Backend"
        ), patch("index_core.sales_history_processor.OpenStampClient"):
            processor = SalesHistoryProcessor()
            processor.db_manager = mock_db_manager  # Replace with mocked db_manager

        # Mock return value for the query
        mock_cursor.fetchone.return_value = (0,)  # Return 0 volume

        volume = processor.calculate_volume_from_history(test_cpid, hours=24)

        assert volume == 0.0

    @pytest.mark.integration
    def test_end_to_end_volume_flow(self):
        """
        Full end-to-end test with real database connection.
        This test is marked as integration and will only run with pytest -m integration.
        """
        # This would test against a real test database
        # Skipped in normal test runs
        pass
