"""
Test cases for the market data job scheduler.

Tests cover job scheduling, batch processing, and database queries
with special focus on the collection ID hex string handling.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from index_core.market_data_jobs import MarketDataJobScheduler


class TestMarketDataJobScheduler:
    """Test cases for MarketDataJobScheduler class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scheduler = MarketDataJobScheduler()

        # Mock database
        self.mock_db = Mock()
        self.mock_cursor = Mock()
        self.mock_db.cursor.return_value = self.mock_cursor

    def test_get_collections_needing_update_returns_hex_strings(self):
        """Test that _get_collections_needing_update returns hex strings not binary."""
        # Mock database returning hex strings (after HEX() function)
        self.mock_cursor.fetchall.return_value = [
            ("EC179CF4CAA43C3A02C6C8B05F3DDAEE",),
            ("D491867E2F53F6C1FFEA92BC1B1FC3AD",),
            ("47D622CE6F26D04B12E82B17C0281312",),
        ]

        result = self.scheduler._get_collections_needing_update(self.mock_db)

        # Verify results are hex strings
        assert len(result) == 3
        assert all(isinstance(cid, str) for cid in result)
        assert all(len(cid) == 32 for cid in result)

        # Verify the SQL query uses HEX()
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]
        assert "SELECT DISTINCT HEX(c.collection_id)" in sql_query

    def test_process_collection_update_no_collection_id_in_data(self):
        """Test that collection_id is not included in the update data dict."""
        collection_id = "EC179CF4CAA43C3A02C6C8B05F3DDAEE"

        with patch("index_core.market_data_jobs.market_data_service") as mock_service:
            self.scheduler._process_collection_update(self.mock_db, collection_id)

            # Get the call to update_collection_market_data
            update_call = mock_service.update_collection_market_data.call_args
            passed_collection_id = update_call[0][0]
            passed_data = update_call[0][1]

            # Verify collection_id is passed as first parameter
            assert passed_collection_id == collection_id

            # Verify collection_id is NOT in the data dict
            assert "collection_id" not in passed_data

            # Verify other expected fields are present
            assert "floor_price_btc" in passed_data
            assert "total_volume_btc" in passed_data
            assert "unique_holders" in passed_data

    def test_process_src20_batch_no_tick_in_data(self):
        """Test that tick is not included in the update data dict."""
        token_ticks = ["TEST1", "TEST2", "TEST3"]

        with patch("index_core.market_data_jobs.market_data_service") as mock_service:
            with patch("index_core.market_data_jobs.SRC20Worker") as mock_worker_class:
                # Mock SRC20Worker instance and its method
                mock_worker = Mock()
                mock_worker_class.return_value = mock_worker
                mock_worker.process_src20_market_data.return_value = {
                    "floor_price_btc": None,
                    "volume_24h_btc": None,
                    "holder_count": None,
                    "primary_exchange": "placeholder",
                    "data_quality_score": 1.0,
                }

                self.scheduler._process_src20_batch(self.mock_db, token_ticks)

            # Verify update was called for each tick
            assert mock_service.update_src20_market_data.call_count == 3

            # Check each call
            for i, tick in enumerate(token_ticks):
                call_args = mock_service.update_src20_market_data.call_args_list[i]
                passed_tick = call_args[0][0]
                passed_data = call_args[0][1]

                # Verify tick is passed as first parameter
                assert passed_tick == tick

                # Verify tick is NOT in the data dict
                assert "tick" not in passed_data

                # Verify expected fields are present
                assert "floor_price_btc" in passed_data
                assert "volume_24h_btc" in passed_data
                assert "holder_count" in passed_data
                assert "primary_exchange" in passed_data
                assert "data_quality_score" in passed_data

    def test_process_stamp_batch_uses_worker(self):
        """Test that stamp batch processing uses StampWorker for detailed analysis."""
        stamp_cpids = ["A1234567890123456789", "A9876543210987654321"]

        # Note: CPIDs are now pre-filtered with ident='STAMP' in SQL, no validation needed
        with patch("index_core.market_data_jobs.StampWorker") as mock_worker_class:
            with patch("index_core.market_data_jobs.market_data_service") as mock_service:
                # Mock StampWorker instance and its method
                mock_worker = Mock()
                mock_worker_class.return_value = mock_worker
                mock_worker.process_stamp_market_data.return_value = {
                    "floor_price_btc": 0.001,
                    "volume_24h_btc": 0.05,
                    "holder_count": 10,
                    "data_source": "counterparty",
                    "data_quality_score": 8.0,
                }

                self.scheduler._process_stamp_batch(self.mock_db, stamp_cpids)

                # Verify StampWorker was created
                mock_worker_class.assert_called_once()

                # Verify worker method was called for each CPID
                assert mock_worker.process_stamp_market_data.call_count == 2
                mock_worker.process_stamp_market_data.assert_any_call("A1234567890123456789")
                mock_worker.process_stamp_market_data.assert_any_call("A9876543210987654321")

                # Verify service was called for each processed stamp
                assert mock_service.update_stamp_market_data.call_count == 2

    def test_process_stamp_batch_processes_all_cpids(self):
        """Test that all provided CPIDs are processed (since they're pre-filtered by SQL)."""
        # CPIDs are now pre-filtered by ident='STAMP' in SQL query, so all should be valid
        stamp_cpids = ["A1234567890123456789", "A9876543210987654321"]

        with patch("index_core.market_data_jobs.StampWorker") as mock_worker_class:
            with patch("index_core.market_data_jobs.market_data_service") as mock_service:
                # Mock StampWorker instance and its method
                mock_worker = Mock()
                mock_worker_class.return_value = mock_worker
                mock_worker.process_stamp_market_data.return_value = {
                    "floor_price_btc": 0.001,
                    "volume_24h_btc": 0.05,
                    "holder_count": 10,
                    "data_source": "counterparty",
                    "data_quality_score": 8.0,
                }

                self.scheduler._process_stamp_batch(self.mock_db, stamp_cpids)

                # Verify StampWorker was created
                mock_worker_class.assert_called_once()

                # Verify worker method was called for all CPIDs (no filtering needed)
                assert mock_worker.process_stamp_market_data.call_count == 2
                mock_worker.process_stamp_market_data.assert_any_call("A1234567890123456789")
                mock_worker.process_stamp_market_data.assert_any_call("A9876543210987654321")

                # Verify service was called for all assets
                assert mock_service.update_stamp_market_data.call_count == 2

    def test_get_stamps_needing_update_query(self):
        """Test the SQL query for getting stamps needing updates."""
        self.mock_cursor.fetchall.return_value = [
            ("CPID1",),
            ("CPID2",),
            ("CPID3",),
        ]

        # Call the method to test the query
        self.scheduler._get_stamps_needing_update(self.mock_db)

        # Verify SQL query structure
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]
        sql_params = execute_call[0][1]

        # Check query components - updated for new optimized query structure
        assert "SELECT DISTINCT s.cpid" in sql_query
        assert "FROM StampTableV4 s" in sql_query
        assert "LEFT JOIN stamp_market_data smd" in sql_query
        assert "WHERE s.ident = 'STAMP'" in sql_query  # New ident filter
        assert "smd.last_updated IS NULL" in sql_query  # Now in AND clause
        assert "OR smd.last_updated < DATE_SUB(NOW(), INTERVAL %s MINUTE)" in sql_query

        # Verify parameters - updated for new limits
        assert len(sql_params) == 2
        assert sql_params[0] == 15  # STAMP_UPDATE_INTERVAL // 60
        assert sql_params[1] == 10000  # STAMP_SELECTION_LIMIT (new value)

    def test_get_src20_tokens_needing_update_query(self):
        """Test the SQL query for getting SRC-20 tokens needing updates."""
        self.mock_cursor.fetchall.return_value = [
            ("TICK1",),
            ("TICK2",),
            ("TICK3",),
        ]

        # Call the method to test the query
        self.scheduler._get_src20_tokens_needing_update(self.mock_db)

        # Verify SQL query structure
        execute_call = self.mock_cursor.execute.call_args
        sql_query = execute_call[0][0]
        sql_params = execute_call[0][1]

        # Check query components
        assert "SELECT DISTINCT s.tick" in sql_query
        assert "FROM SRC20Valid s" in sql_query
        assert "LEFT JOIN src20_market_data smd" in sql_query

        # Verify parameters
        assert len(sql_params) == 2
        assert sql_params[0] == 5  # SRC20_UPDATE_INTERVAL // 60
        assert sql_params[1] == 1000  # SRC20_SELECTION_LIMIT (new value)

    def test_error_handling_in_get_collections(self):
        """Test error handling when database query fails."""
        self.mock_cursor.execute.side_effect = Exception("Database error")

        result = self.scheduler._get_collections_needing_update(self.mock_db)

        # Should return empty list on error
        assert result == []

    def test_split_into_batches(self):
        """Test the batch splitting utility function."""
        items = list(range(10))

        # Test with batch size 3
        batches = self.scheduler._split_into_batches(items, 3)

        assert len(batches) == 4  # 10 items / 3 per batch = 4 batches
        assert batches[0] == [0, 1, 2]
        assert batches[1] == [3, 4, 5]
        assert batches[2] == [6, 7, 8]
        assert batches[3] == [9]

        # Test with exact batch size
        batches = self.scheduler._split_into_batches(items, 5)
        assert len(batches) == 2
        assert len(batches[0]) == 5
        assert len(batches[1]) == 5

    def test_update_stamp_market_data_job_integration(self):
        """Test the full stamp market data update job flow."""
        # Setup mocks - mock the database manager connection instead of initialize_db
        self.mock_cursor.fetchall.return_value = [("CPID1",), ("CPID2",)]

        # Mock the database manager connection
        with patch.object(self.scheduler.database_manager, "connect", return_value=self.mock_db):
            with patch("index_core.market_data_jobs.StampWorker") as mock_worker_class:
                with patch("index_core.market_data_jobs.market_data_service") as mock_service:
                    # Note: CPIDs are now pre-filtered with ident='STAMP' in SQL, no validation needed
                    # Mock StampWorker instance and its method
                    mock_worker = Mock()
                    mock_worker_class.return_value = mock_worker
                    mock_worker.process_stamp_market_data.return_value = {
                        "floor_price_btc": 0.001,
                        "volume_24h_btc": 0.05,
                        "holder_count": 10,
                        "data_source": "counterparty",
                        "data_quality_score": 8.0,
                    }

                    # Run the job
                    self.scheduler._update_stamp_market_data_job()

                    # Verify StampWorker was used
                    mock_worker_class.assert_called()

                    # Verify worker method was called for each CPID
                    assert mock_worker.process_stamp_market_data.call_count == 2
                    mock_worker.process_stamp_market_data.assert_any_call("CPID1")
                    mock_worker.process_stamp_market_data.assert_any_call("CPID2")

                    # Verify service was called for each asset
                    assert mock_service.update_stamp_market_data.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__])
