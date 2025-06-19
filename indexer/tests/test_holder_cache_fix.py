#!/usr/bin/env python3
"""
Test suite for holder cache functionality fix.

This test validates that the StampWorker correctly generates and extracts
holder cache data for database population.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add src directory to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def mock_counterparty_api():
    """Mock the Counterparty API responses."""

    def mock_api_response(endpoint, params):
        if "dispensers" in endpoint:
            return {"result": [{"status": 0, "satoshirate": "1000", "give_quantity": "100"}]}
        elif "dispenses" in endpoint:
            return {"result": [{"block_time": 1700000000, "satoshirate": "1500", "dispense_quantity": "10"}]}
        elif "balances" in endpoint:
            return {
                "result": [
                    {"address": "1TestAddress1", "quantity": "100.50000000"},
                    {"address": "1TestAddress2", "quantity": "50.25000000"},
                    {"address": "1TestAddress3", "quantity": "25.12500000"},
                ]
            }
        return None

    with patch("index_core.stamp_worker.fetch_xcp", side_effect=mock_api_response):
        yield mock_api_response


@pytest.fixture
def mock_invalid_balances_api():
    """Mock Counterparty API with invalid balance data."""

    def mock_api_response(endpoint, params):
        if "dispensers" in endpoint:
            return {"result": []}
        elif "dispenses" in endpoint:
            return {"result": []}
        elif "balances" in endpoint:
            return {
                "result": [
                    {"address": "", "quantity": "10.00000000"},  # Empty address
                    {"address": "1TestAddress", "quantity": "0.00000000"},  # Zero quantity
                    {"address": "1TestAddress2", "quantity": ""},  # Empty quantity
                    {"address": "1TestAddress3"},  # Missing quantity
                ]
            }
        return None

    with patch("index_core.stamp_worker.fetch_xcp", side_effect=mock_api_response):
        yield mock_api_response


class TestHolderCacheFix:
    """Test suite for holder cache functionality."""

    def test_holder_cache_data_generation(self, mock_counterparty_api):
        """Test that StampWorker generates holder cache data correctly."""
        # Mock the DatabaseManager in StampMarketDataProcessor
        with patch("index_core.stamp_market_processor.DatabaseManager") as mock_db_manager:
            mock_db_manager.return_value.connect.return_value = None

            from index_core.stamp_worker import StampWorker

            stamp_worker = StampWorker()

            # Test direct holder metrics calculation
            mock_balances = [
                {"address": "1TestAddress1", "quantity": "100.50000000"},
                {"address": "1TestAddress2", "quantity": "50.25000000"},
                {"address": "1TestAddress3", "quantity": "25.12500000"},
            ]

            holder_metrics = stamp_worker._calculate_holder_metrics(mock_balances)

            # Verify holder count
            assert holder_metrics["holder_count"] == 3

            # Verify holder cache data exists
            assert "holder_cache_data" in holder_metrics
            holder_cache_data = holder_metrics["holder_cache_data"]

            # Verify structure and content
            assert len(holder_cache_data) == 3
            assert all("address" in holder and "quantity" in holder for holder in holder_cache_data)
            assert all(isinstance(holder["quantity"], float) and holder["quantity"] > 0 for holder in holder_cache_data)

            # Verify specific data
            addresses = [holder["address"] for holder in holder_cache_data]
            assert "1TestAddress1" in addresses
            assert "1TestAddress2" in addresses
            assert "1TestAddress3" in addresses

    def test_holder_cache_data_extraction(self, mock_counterparty_api):
        """Test that StampWorker extracts holder cache data for database population."""
        # Mock the DatabaseManager in StampMarketDataProcessor
        with patch("index_core.stamp_market_processor.DatabaseManager") as mock_db_manager:
            mock_db_manager.return_value.connect.return_value = None

            from index_core.stamp_worker import StampWorker

            stamp_worker = StampWorker()
            test_cpid = "A17381709725340633000"

            # Process market data
            market_data = stamp_worker.process_stamp_market_data(test_cpid)

            # Verify market data was generated
            assert market_data is not None
            assert market_data["cpid"] == test_cpid
            assert market_data["holder_count"] == 3

            # Verify holder cache data was extracted
            assert "_holder_cache_data" in market_data
            holder_cache_data = market_data["_holder_cache_data"]

            # Verify extracted data structure
            assert len(holder_cache_data) == 3
            assert all("address" in holder and "quantity" in holder for holder in holder_cache_data)

            # Verify holder_cache_data was removed from main market data
            assert "holder_cache_data" not in market_data

    def test_holder_cache_with_invalid_balances(self, mock_invalid_balances_api):
        """Test that invalid balances are properly filtered out."""
        # Mock the DatabaseManager in StampMarketDataProcessor
        with patch("index_core.stamp_market_processor.DatabaseManager") as mock_db_manager:
            mock_db_manager.return_value.connect.return_value = None

            from index_core.stamp_worker import StampWorker

            stamp_worker = StampWorker()

            # Test with invalid balance data
            mock_invalid_balances = [
                {"address": "", "quantity": "10.00000000"},  # Empty address
                {"address": "1TestAddress", "quantity": "0.00000000"},  # Zero quantity
                {"address": "1TestAddress2", "quantity": ""},  # Empty quantity
                {"address": "1TestAddress3"},  # Missing quantity
            ]

            holder_metrics = stamp_worker._calculate_holder_metrics(mock_invalid_balances)

            # Verify no valid holders found
            assert holder_metrics["holder_count"] == 0

            # Verify no holder cache data generated for invalid balances
            assert "holder_cache_data" not in holder_metrics

    def test_populate_holder_cache_database_logic(self):
        """Test the database population logic with mocked database."""
        from index_core.market_data_jobs import MarketDataJobScheduler

        # Mock database and cursor with proper context manager support
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db.cursor.return_value.__exit__.return_value = None
        mock_cursor.execute = MagicMock()
        mock_cursor.executemany = MagicMock()
        mock_cursor.fetchone = MagicMock(return_value=[3])  # Mock count result
        mock_cursor.rowcount = 3

        # Test holder data
        test_cpid = "A17381709725340633000"
        test_holder_data = [
            {"address": "1TestAddress1", "quantity": 100.0},
            {"address": "1TestAddress2", "quantity": 50.0},
            {"address": "1TestAddress3", "quantity": 25.0},
        ]

        # Test the populate method
        scheduler = MarketDataJobScheduler()
        scheduler._populate_holder_cache(mock_db, test_cpid, test_holder_data)

        # Verify DELETE was called (cleanup existing data)
        delete_calls = [call for call in mock_cursor.execute.call_args_list if call[0] and "DELETE" in call[0][0]]
        assert len(delete_calls) == 1

        # Verify INSERT was called
        assert mock_cursor.executemany.call_count == 1

        # Verify INSERT statement structure
        insert_call = mock_cursor.executemany.call_args
        insert_sql = insert_call[0][0]
        insert_values = insert_call[0][1]

        assert "INSERT INTO stamp_holder_cache" in insert_sql
        assert len(insert_values) == 3

        # Verify data structure in insert values
        for i, values in enumerate(insert_values):
            assert values[0] == test_cpid  # cpid
            assert values[1] in ["1TestAddress1", "1TestAddress2", "1TestAddress3"]  # address
            assert isinstance(values[2], float)  # quantity
            assert values[4] == i + 1  # rank_position (1-based)
            assert values[5] == "counterparty"  # balance_source

    def test_integration_holder_cache_workflow(self, mock_counterparty_api):
        """Test the complete integration workflow from data generation to extraction."""
        with patch("index_core.stamp_market_processor.DatabaseManager") as mock_db_manager:
            mock_db_manager.return_value.connect.return_value = None

            from index_core.stamp_worker import StampWorker

            # Step 1: Generate market data with holder cache
            stamp_worker = StampWorker()
            test_cpid = "A17381709725340633000"
            market_data = stamp_worker.process_stamp_market_data(test_cpid)

            # Verify data was generated
            assert market_data is not None
            assert "_holder_cache_data" in market_data

            # Step 2: Extract holder cache data (simulate scheduler workflow)
            holder_cache_data = market_data.pop("_holder_cache_data", None)
            assert holder_cache_data is not None
            assert len(holder_cache_data) == 3

            # Step 3: Verify data structure for database population
            for holder in holder_cache_data:
                assert "address" in holder
                assert "quantity" in holder
                assert isinstance(holder["quantity"], float)
                assert holder["quantity"] > 0
                assert holder["address"].startswith("1Test")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
