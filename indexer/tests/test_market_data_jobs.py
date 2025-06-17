"""
Test cases for the market data job scheduler.

Tests cover job scheduling, batch processing, and database queries
with special focus on the collection ID hex string handling.
"""

import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from index_core.market_data_jobs import MarketDataJobScheduler


class TestMarketDataJobScheduler:
    """Test cases for MarketDataJobScheduler class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scheduler = MarketDataJobScheduler()

        # Mock database connection with proper context manager support
        self.mock_db = MagicMock()
        self.mock_cursor = MagicMock()
        # Configure cursor to work with context manager
        cursor_context = MagicMock()
        cursor_context.__enter__ = MagicMock(return_value=self.mock_cursor)
        cursor_context.__exit__ = MagicMock(return_value=None)
        self.mock_db.cursor.return_value = cursor_context

    def test_get_collections_needing_update_returns_hex_strings(self):
        """Test that _get_collections_needing_update returns hex strings not binary."""
        # Mock cursor returns itself
        self.mock_db.cursor.return_value = self.mock_cursor
        # Add close method
        self.mock_cursor.close = Mock()

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

    def test_get_stamps_needing_update_calls_database_function(self):
        """Test that _get_stamps_needing_update uses the database function correctly."""
        expected_cpids = ["A1234567890123456789", "FUCKTHAT", "LEGENDARYBAR"]

        # Patch the database function
        with patch("index_core.database.get_stamps_needing_market_update") as mock_get_stamps:
            mock_get_stamps.return_value = expected_cpids

            # Call the method
            result = self.scheduler._get_stamps_needing_update(self.mock_db)

            # Verify the database function was called with correct parameters
            mock_get_stamps.assert_called_once_with(
                self.mock_db,
                update_interval_minutes=15,  # STAMP_UPDATE_INTERVAL // 60
                limit=10000,  # STAMP_SELECTION_LIMIT (new value)
            )

            # Verify result is returned correctly
            assert result == expected_cpids

    def test_src20_job_uses_bulk_fetch(self):
        """Test that SRC-20 job uses bulk fetch from OpenStamp."""
        with patch("index_core.market_data_jobs.SRC20Worker") as mock_worker_class:
            with patch("index_core.market_data_jobs.market_data_service") as mock_service:
                # Mock the database manager
                with patch.object(self.scheduler.database_manager, "connect") as mock_connect:
                    mock_connect.return_value = self.mock_db
                    # Add mock for close method
                    self.mock_db.close = Mock()

                    # Mock the database query for tokens
                    self.mock_cursor.fetchall.return_value = [
                        ("TEST",),
                        ("PEPE",),
                        ("RARE",),
                    ]

                    # Mock worker and its methods
                    mock_worker = Mock()
                    mock_worker_class.return_value = mock_worker

                    # Mock bulk fetch returning all tokens at once
                    mock_worker.fetch_all_openstamp_data.return_value = [
                        {"name": "TEST", "price": "100000000"},
                        {"name": "PEPE", "price": "50000000"},
                        {"name": "RARE", "price": "200000000"},
                    ]

                    # Mock transform method
                    mock_worker.transform_openstamp_data.side_effect = [
                        {"tick": "TEST", "price_btc": 1.0},
                        {"tick": "PEPE", "price_btc": 0.5},
                        {"tick": "RARE", "price_btc": 2.0},
                    ]

                    # Mock STAMP processing
                    mock_worker.process_src20_market_data.return_value = {"tick": "STAMP", "price_btc": 0.001}

                    # Run the job
                    self.scheduler._update_src20_market_data_job()

                    # Verify bulk fetch was called once
                    mock_worker.fetch_all_openstamp_data.assert_called_once()

                    # Verify transform was called for each token
                    assert mock_worker.transform_openstamp_data.call_count == 3

                    # Verify market data service was updated for each token
                    assert mock_service.update_src20_market_data.call_count == 4  # 3 from OpenStamp + 1 STAMP

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
        # Mock the database manager connection
        with patch.object(self.scheduler.database_manager, "connect", return_value=self.mock_db):
            # Mock the database function to return specific CPIDs
            with patch("index_core.database.get_stamps_needing_market_update") as mock_get_stamps:
                mock_get_stamps.return_value = ["CPID1", "CPID2"]

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

    def test_src20_case_sensitivity_handling(self):
        """Test that SRC-20 tokens from OpenStamp are matched case-insensitively with database."""
        with patch("index_core.market_data_jobs.SRC20Worker") as mock_worker_class:
            with patch("index_core.market_data_jobs.market_data_service") as mock_service:
                # Mock the database manager
                with patch.object(self.scheduler.database_manager, "connect") as mock_connect:
                    mock_connect.return_value = self.mock_db
                    # Add mock for close method
                    self.mock_db.close = Mock()

                    # Mock the database query for tokens (case variations)
                    self.mock_cursor.fetchall.return_value = [
                        ("stamp",),  # lowercase in database
                        ("PePe",),  # mixed case in database
                        ("BIAO",),  # uppercase in database
                    ]

                    # Mock worker
                    mock_worker = Mock()
                    mock_worker_class.return_value = mock_worker

                    # OpenStamp returns uppercase tokens
                    mock_worker.fetch_all_openstamp_data.return_value = [
                        {"name": "STAMP", "price": "100000000"},
                        {"name": "PEPE", "price": "50000000"},
                        {"name": "BIAO", "price": "75000000"},
                    ]

                    # Mock transform to verify case handling
                    def transform_side_effect(token_data):
                        return {
                            "tick": token_data["name"],  # Keep uppercase from OpenStamp
                            "price_btc": int(token_data["price"]) / 100000000,
                        }

                    mock_worker.transform_openstamp_data.side_effect = transform_side_effect

                    # Run the job
                    self.scheduler._update_src20_market_data_job()

                    # Verify all tokens were processed with database case preserved
                    calls = mock_service.update_src20_market_data.call_args_list
                    processed_ticks = [call[0][0] for call in calls]

                    # The implementation preserves database case, not OpenStamp case
                    assert "stamp" in processed_ticks  # lowercase as in database
                    assert "PePe" in processed_ticks  # mixed case as in database
                    assert "BIAO" in processed_ticks  # uppercase as in database

                    # Also verify STAMP special handling (always processed)
                    assert "STAMP" in processed_ticks  # STAMP is always added

    def test_stamp_kucoin_case_matching(self):
        """Test that STAMP token matches KuCoin exchange mapping regardless of case."""
        from index_core.src20_worker import SRC20Worker

        worker = SRC20Worker()

        # Mock the KuCoin API calls and reliability tracking
        with patch.object(worker, "_fetch_kucoin_data") as mock_kucoin:
            with patch.object(worker, "_fetch_openstamp_data") as mock_openstamp:
                with patch.object(worker, "_fetch_stampscan_data") as mock_stampscan:
                    with patch("index_core.src20_worker.create_reliability_tracker") as mock_tracker:
                        with patch("index_core.src20_worker.record_call_metrics"):
                            # Mock the reliability tracker
                            mock_tracker_instance = MagicMock()
                            mock_tracker.return_value = mock_tracker_instance

                            mock_kucoin.return_value = {"price_btc": 0.00001, "volume_24h_btc": 10.5, "data_source": "kucoin"}
                            mock_openstamp.return_value = None
                            mock_stampscan.return_value = None

                            # Test with lowercase 'stamp' from database
                            result = worker.process_src20_market_data("stamp")

                            # Should have called KuCoin fetch despite case difference
                            mock_kucoin.assert_called_once()
                            assert result is not None
                            assert result.get("primary_exchange") == "kucoin"
                            assert "kucoin" in result.get("sources", [])

    def test_src20_emoji_escape_sequence_handling(self):
        """Test that emoji tokens with escape sequences are handled correctly."""
        # Set up environment for test
        import os

        from index_core.src20_worker import SRC20Worker
        from index_core.types import OpenStampApiResponse

        os.environ["OPENSTAMP_API_KEY"] = "test_key"

        try:
            with patch("index_core.src20_worker.create_reliability_tracker") as mock_tracker:
                with patch("index_core.src20_worker.record_call_metrics"):
                    # Mock the reliability tracker
                    mock_tracker_instance = MagicMock()
                    mock_tracker.return_value = mock_tracker_instance

                    worker = SRC20Worker()

                    # Database has escape sequence
                    db_token = "lumi\\U0001f4ab"

                    # Mock OpenStamp response with actual emoji
                    mock_response_data = {
                        "code": 200,
                        "data": [
                            {
                                "tokenId": 1,
                                "name": "lumi💫",  # Actual emoji
                                "totalSupply": 1000000,
                                "holdersCount": 50,
                                "price": "100000000",
                                "amount24": "0",
                                "volume24": "5000000000",
                                "volume24Change": "0.1",
                                "change24": "0.05",
                                "change7d": "0.15",
                            }
                        ],
                    }

                    mock_api_response = OpenStampApiResponse(mock_response_data)

                    # Set up the cache to avoid API calls
                    worker._openstamp_cache = mock_api_response
                    worker._openstamp_cache_time = 9999999999  # Far future

                    # Test the fetch
                    result = worker._fetch_openstamp_data(db_token)

                    # Should find the token despite encoding difference
                    assert result is not None
                    assert result["tick"] == "lumi💫"
                    assert result["data_source"] == "openstamp"

        finally:
            # Clean up
            if "OPENSTAMP_API_KEY" in os.environ:
                del os.environ["OPENSTAMP_API_KEY"]

    def test_openstamp_api_caching_prevents_repeated_calls(self):
        """Test that OpenStamp API caching prevents repeated API calls."""
        # Set up environment
        import os

        from index_core.src20_worker import SRC20Worker

        os.environ["OPENSTAMP_API_KEY"] = "test_key"

        try:
            worker = SRC20Worker()

            # Mock the OpenStamp client
            with patch("index_core.src20_worker.get_openstamp_client") as mock_client:
                mock_response = Mock()
                mock_response.get_all_tickers.return_value = ["STAMP", "PEPE", "RARE"]
                mock_client.return_value.fetch_all_market_data.return_value = mock_response

                # First call should fetch from API
                result1 = worker.get_all_available_tokens()
                assert len(result1) == 3
                assert mock_client.return_value.fetch_all_market_data.call_count == 1

                # Second call should use cache
                result2 = worker.get_all_available_tokens()
                assert len(result2) == 3
                # Should still be 1 call, not 2
                assert mock_client.return_value.fetch_all_market_data.call_count == 1

                # Force cache expiry
                worker._openstamp_cache_time = 0

                # Third call should fetch again
                result3 = worker.get_all_available_tokens()
                assert len(result3) == 3
                assert mock_client.return_value.fetch_all_market_data.call_count == 2

        finally:
            if "OPENSTAMP_API_KEY" in os.environ:
                del os.environ["OPENSTAMP_API_KEY"]


if __name__ == "__main__":
    pytest.main([__file__])
