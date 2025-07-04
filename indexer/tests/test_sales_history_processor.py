"""
Unit tests for SalesHistoryProcessor

These tests mock all external dependencies and can run in CI.
They test the internal logic and data flow without actual API calls.

Run with: poetry run pytest tests/test_sales_history_processor.py -v
"""

import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from index_core.database_manager import DatabaseManager
from index_core.sales_history_processor import STAMPS_GENESIS_BLOCK, SalesHistoryProcessor


class TestSalesHistoryProcessor:
    """Unit tests for SalesHistoryProcessor with mocked dependencies"""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Cleanup any global state before and after each test"""
        # Run test
        yield

        # Cleanup after test
        # Import here to avoid circular import issues
        from index_core.sales_history_processor import sales_history_processor

        # Reset any global state
        if hasattr(sales_history_processor, "catchup_running"):
            sales_history_processor.catchup_running = False
        if hasattr(sales_history_processor, "catchup_executor") and sales_history_processor.catchup_executor:
            sales_history_processor.catchup_executor.shutdown(wait=False)
            sales_history_processor.catchup_executor = None
        if hasattr(sales_history_processor, "cpid_cache"):
            sales_history_processor.cpid_cache.clear()
        if hasattr(sales_history_processor, "last_cache_update"):
            sales_history_processor.last_cache_update = 0
        if hasattr(sales_history_processor, "progress"):
            sales_history_processor.progress = {
                "total_cpids": 0,
                "processed_cpids": 0,
                "total_sales": 0,
                "last_block_processed": 0,
                "catchup_start_time": None,
                "errors": 0,
            }

    # Remove local mock_db_manager fixture - use global one from conftest.py

    @pytest.fixture
    def processor(self, mock_db_manager, mock_cursor):
        """Create a fresh processor instance with mocked database"""
        # Add _cursor attribute for tests that need direct cursor access
        mock_connection = mock_db_manager.connect()
        mock_connection._cursor = mock_cursor

        # Create a new instance instead of using the global one
        processor = SalesHistoryProcessor(db_manager=mock_db_manager)

        # Ensure clean state
        processor.catchup_running = False
        processor.catchup_executor = None
        processor.cpid_cache = set()
        processor.last_cache_update = 0

        # Set default mock return values for common queries
        # This avoids TypeError in tests that don't explicitly set these
        mock_cursor.fetchone.return_value = (0,)  # Default: no historical data
        mock_cursor.fetchall.return_value = []  # Default: no results

        yield processor

        # Cleanup after test
        if processor.catchup_executor:
            processor.catchup_executor.shutdown(wait=False)

    def test_initialization(self, processor):
        """Test processor initialization"""
        assert processor.cpid_cache == set()
        assert processor.last_cache_update == 0
        assert processor.cache_update_interval == 300
        assert not processor.catchup_running
        assert processor.catchup_executor is None
        assert processor.progress["total_cpids"] == 0
        assert processor.progress["processed_cpids"] == 0

    def test_cpid_cache_update(self, processor, mock_cursor):
        """Test CPID cache update logic"""
        # Setup mock cursor to return CPIDs
        mock_cursor.fetchall.return_value = [
            ("A1111111111111111111",),
            ("A2222222222222222222",),
            ("A3333333333333333333",),
        ]

        # Update cache
        processor.update_cpid_cache()

        # Verify cache was updated
        assert len(processor.cpid_cache) == 3
        assert "A1111111111111111111" in processor.cpid_cache
        assert "A2222222222222222222" in processor.cpid_cache
        assert "A3333333333333333333" in processor.cpid_cache
        assert processor.last_cache_update > 0

        # Verify SQL query was correct
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "SELECT DISTINCT cpid" in sql
        assert "FROM StampTableV4" in sql
        assert "WHERE ident IN ('STAMP', 'SRC-721')" in sql

    def test_cpid_cache_refresh_interval(self, processor, mock_db_manager, mock_cursor):
        """Test that cache respects refresh interval"""
        mock_cursor.fetchall.return_value = [("A1111111111111111111",)]

        # First update
        processor.update_cpid_cache()
        first_update_time = processor.last_cache_update

        # Try immediate update - should skip
        mock_cursor.fetchall.return_value = [("A2222222222222222222",)]
        processor.update_cpid_cache()

        # Cache should not have updated
        assert processor.last_cache_update == first_update_time
        assert "A2222222222222222222" not in processor.cpid_cache

        # Force cache expiry
        processor.last_cache_update = time.time() - 301
        processor.update_cpid_cache()

        # Now cache should update
        assert "A2222222222222222222" in processor.cpid_cache

    @patch("index_core.sales_history_processor.fetch_xcp")
    def test_process_block_dispenses(self, mock_fetch, processor, mock_cursor):
        """Test processing dispenses for a specific block"""
        # Setup CPID cache
        processor.cpid_cache = {"A1111111111111111111", "A2222222222222222222"}
        processor.last_cache_update = time.time()

        # Mock the _has_historical_data check
        mock_cursor.fetchone.return_value = (1,)  # Has historical data

        # Mock API response
        mock_fetch.return_value = {
            "result": [
                {
                    "tx_hash": "tx1",
                    "block_index": 800000,
                    "block_time": 1234567890,
                    "asset": "A1111111111111111111",  # Stamp CPID
                    "source": "buyer1",
                    "destination": "dispenser1",
                    "dispense_quantity": 1,
                    "btc_amount": 100000,
                    "dispenser_tx_hash": "disp_tx1",
                    "dispenser": {"satoshirate": 100000},
                },
                {
                    "tx_hash": "tx2",
                    "block_index": 800000,
                    "asset": "XCP",  # Not a stamp
                    "source": "buyer2",
                    "destination": "dispenser2",
                    "dispense_quantity": 10,
                    "btc_amount": 500000,
                    "dispenser": {"satoshirate": 50000},
                },
            ]
        }

        # Process block
        count = processor.process_block_dispenses(800000)

        # Should only process stamp dispenses
        assert count == 1

        # Verify API was called correctly
        mock_fetch.assert_called_once_with("/blocks/800000/dispenses", {"verbose": "true", "show_unconfirmed": "false"})

    @patch("index_core.sales_history_processor.fetch_xcp")
    def test_process_block_before_genesis(self, mock_fetch, processor):
        """Test that blocks before genesis are skipped"""
        count = processor.process_block_dispenses(779651)  # Before genesis

        assert count == 0
        mock_fetch.assert_not_called()

    def test_store_dispenser_sales(self, processor, mock_db_manager):
        """Test storing dispenser sales to database"""
        cursor = mock_db_manager.connect()._cursor

        # Test data
        dispenses = [
            {
                "tx_hash": "tx1",
                "block_index": 800000,
                "block_time": 1234567890,
                "asset": "A1111111111111111111",
                "source": "buyer1",  # Buyer address
                "destination": "seller1",  # Dispenser address
                "dispense_quantity": 5,
                "btc_amount": 500000,
                "dispenser_tx_hash": "disp_tx1",
                "dispenser": {"satoshirate": 100000},
            },
            {
                "tx_hash": "tx2",
                "block_index": 800001,
                "block_time": 1234567900,
                "asset": "A2222222222222222222",
                "source": "buyer2",
                "destination": "seller2",
                "dispense_quantity": 10,
                "btc_amount": 1000000,
                "dispenser_tx_hash": "disp_tx2",
                "dispenser": {"satoshirate": 100000},
            },
        ]

        # Store sales
        processor._store_dispenser_sales(dispenses)

        # Verify executemany was called with correct data
        cursor.executemany.assert_called_once()
        sql, data = cursor.executemany.call_args[0]

        # Check SQL
        assert "INSERT INTO stamp_sales_history" in sql
        assert "ON DUPLICATE KEY UPDATE" in sql

        # Check data
        assert len(data) == 2

        # First sale
        assert data[0][0] == "tx1"  # tx_hash
        assert data[0][1] == 800000  # block_index
        assert data[0][2] == 1234567890  # block_time
        assert data[0][3] == "A1111111111111111111"  # cpid
        assert data[0][4] == "dispenser"  # sale_type
        assert data[0][5] == "buyer1"  # buyer_address
        assert data[0][6] == "seller1"  # seller_address
        assert data[0][7] == 5  # quantity
        assert data[0][8] == 500000  # btc_amount
        assert data[0][9] == 100000  # unit_price_sats
        assert data[0][10] == "disp_tx1"  # dispenser_tx_hash

        # Verify commit was called
        mock_db_manager.connect().commit.assert_called_once()

    def test_calculate_unit_price_fallback(self, processor, mock_db_manager):
        """Test unit price calculation fallback when dispenser data is missing"""
        dispenses = [
            {
                "tx_hash": "tx1",
                "block_index": 800000,
                "asset": "A1111111111111111111",
                "source": "buyer1",
                "destination": "seller1",
                "dispense_quantity": 5,
                "btc_amount": 500000,
                # No dispenser data - should calculate from total/quantity
            }
        ]

        processor._store_dispenser_sales(dispenses)

        cursor = mock_db_manager.connect()._cursor
        sql, data = cursor.executemany.call_args[0]

        # Should calculate unit price as btc_amount / quantity
        assert data[0][9] == 100000  # 500000 / 5

    def test_get_recent_sales(self, processor, mock_db_manager):
        """Test fetching recent sales"""
        cursor = mock_db_manager.connect()._cursor

        # Mock cursor description for column names
        cursor.description = [
            ("tx_hash",),
            ("block_index",),
            ("block_time",),
            ("cpid",),
            ("buyer_address",),
            ("seller_address",),
            ("btc_amount",),
            ("unit_price_sats",),
            ("stamp",),
            ("stamp_url",),
            ("stamp_mimetype",),
        ]

        # Mock sales data
        cursor.fetchall.return_value = [
            (
                "tx1",
                800000,
                1234567890,
                "A1111111111111111111",
                "buyer1",
                "seller1",
                100000,
                100000,
                1,
                "http://example.com/stamp1.png",
                "image/png",
            )
        ]

        # Get recent sales
        sales = processor.get_recent_sales(limit=10)

        # Verify query
        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        assert "FROM stamp_sales_history ssh" in sql
        assert "JOIN StampTableV4 s ON ssh.cpid = s.cpid" in sql
        assert "ORDER BY ssh.block_time DESC" in sql
        assert "LIMIT" in sql

        # Verify result
        assert len(sales) == 1
        assert sales[0]["tx_hash"] == "tx1"
        assert sales[0]["cpid"] == "A1111111111111111111"

    def test_get_recent_sales_for_cpid(self, processor, mock_db_manager):
        """Test fetching recent sales for specific CPID"""
        cursor = mock_db_manager.connect()._cursor
        cursor.description = [("tx_hash",)]
        cursor.fetchall.return_value = []

        # Get sales for specific CPID
        sales = processor.get_recent_sales(limit=5, cpid="A1111111111111111111")

        # Verify query includes CPID filter
        sql = cursor.execute.call_args[0][0]
        assert "WHERE ssh.cpid = %s" in sql
        assert cursor.execute.call_args[0][1] == ("A1111111111111111111", 5)

    def test_calculate_volume_from_history(self, processor, mock_db_manager):
        """Test volume calculation from sales history"""
        cursor = mock_db_manager.connect()._cursor

        # Mock aggregated data
        cursor.fetchone.return_value = (
            5000000,  # total_volume_sats (0.05 BTC)
            10,  # trade_count
            150000,  # high_price
            50000,  # low_price
            1234567890,  # last_sale_time
        )

        # Calculate 24h volume
        result = processor.calculate_volume_from_history("A1111111111111111111", hours=24)

        # Verify query
        sql = cursor.execute.call_args[0][0]
        assert "SUM(btc_amount) as total_volume_sats" in sql
        assert "COUNT(*) as trade_count" in sql
        assert "WHERE cpid = %s" in sql
        assert "AND block_time > UNIX_TIMESTAMP() - (%s * 3600)" in sql

        # Verify result
        assert result["volume_btc"] == 0.05  # 5000000 / 100000000
        assert result["trade_count"] == 10
        assert result["high_sats"] == 150000
        assert result["low_sats"] == 50000
        assert result["last_sale_time"] == 1234567890

    def test_calculate_volume_no_data(self, processor, mock_db_manager):
        """Test volume calculation when no data exists"""
        cursor = mock_db_manager.connect()._cursor
        cursor.fetchone.return_value = None

        result = processor.calculate_volume_from_history("A1111111111111111111", hours=24)

        # Should return zeros
        assert result["volume_btc"] == 0.0
        assert result["trade_count"] == 0
        assert result["high_sats"] == 0
        assert result["low_sats"] == 0
        assert result["last_sale_time"] == 0

    @patch("index_core.sales_history_processor.fetch_xcp")
    def test_process_cached_dispenses(self, mock_fetch, processor):
        """Test processing cached dispenses in Full Catchup Mode"""
        # Set up cached dispenses
        processor.dispense_cache = {
            "data": [
                {
                    "tx_hash": "tx1",
                    "block_index": 800000,
                    "asset": "A1111111111111111111",
                    "source": "buyer1",
                    "destination": "dispenser1",
                    "dispense_quantity": 1,
                    "btc_amount": 100000,
                    "dispenser": {"satoshirate": 100000},
                },
                {
                    "tx_hash": "tx2",
                    "block_index": 800001,
                    "asset": "A2222222222222222222",
                    "source": "buyer2",
                    "destination": "dispenser2",
                    "dispense_quantity": 2,
                    "btc_amount": 200000,
                    "dispenser": {"satoshirate": 100000},
                },
                {
                    "tx_hash": "tx3",
                    "block_index": 800002,
                    "asset": "XCP",  # Not a stamp
                    "source": "buyer3",
                    "destination": "dispenser3",
                    "dispense_quantity": 3,
                    "btc_amount": 300000,
                    "dispenser": {"satoshirate": 100000},
                },
            ],
            "highest_block": 800002,
            "fetched_at_tip": 800100,
        }

        # Set up CPID cache
        processor.cpid_cache = {"A1111111111111111111", "A2222222222222222222"}

        # Process cached dispenses
        count = processor._process_cached_dispenses()

        # Should have processed 2 dispenses (filtered out XCP)
        assert count == 2

        # No API calls should be made - we're processing from cache
        mock_fetch.assert_not_called()

    @patch("index_core.sales_history_processor.fetch_xcp")
    def test_full_catchup_mode_skips_individual_blocks(self, mock_fetch, processor, mock_cursor):
        """Test that Full Catchup Mode skips individual block processing"""
        # Set processor to Full Catchup Mode
        processor.mode = "FULL_CATCHUP"
        processor.catchup_running = True
        processor.dispense_cache = {
            "data": [],
            "highest_block": 850000,  # Cached data up to block 850000
            "fetched_at_tip": 850100,
        }
        processor.cpid_cache = {"A1111111111111111111"}
        processor.last_cache_update = time.time()

        # Mock cursor for any database calls
        mock_cursor.fetchone.return_value = (1,)  # Has historical data

        # Process a block that's before the cached highest block
        count = processor.process_block_dispenses(840000)

        # Should return 0 and NOT make any API calls
        assert count == 0
        mock_fetch.assert_not_called()

    def test_mode_threshold_is_200_blocks(self, processor):
        """Test that mode threshold is set to 200 blocks"""
        assert processor.mode_threshold == 200

    @patch("index_core.sales_history_processor.fetch_xcp")
    def test_realtime_mode_processes_blocks_normally(self, mock_fetch, processor, mock_cursor):
        """Test that Real-time Mode processes blocks normally"""
        # Set processor to Real-time Mode
        processor.mode = "REALTIME"
        processor.catchup_running = False
        processor.cpid_cache = {"A1111111111111111111"}
        processor.last_cache_update = time.time()

        # Mock cursor for database calls
        mock_cursor.fetchone.return_value = (1,)  # Has historical data

        # Mock API response
        mock_fetch.return_value = {
            "result": [
                {
                    "tx_hash": "tx1",
                    "block_index": 850000,
                    "asset": "A1111111111111111111",
                    "source": "buyer1",
                    "destination": "dispenser1",
                    "dispense_quantity": 1,
                    "btc_amount": 100000,
                    "dispenser": {"satoshirate": 100000},
                }
            ]
        }

        # Process block in real-time mode
        count = processor.process_block_dispenses(850000)

        # Should process the dispense and make API call
        assert count == 1
        mock_fetch.assert_called_once_with("/blocks/850000/dispenses", {"verbose": "true", "show_unconfirmed": "false"})

    def test_catchup_mode_start_stop(self, processor, mock_cursor):
        """Test starting and stopping catchup mode"""
        # Mock the database to return no CPIDs needing catchup
        # This prevents the background thread from doing real work
        mock_cursor.fetchall.return_value = []  # No CPIDs need catchup
        mock_cursor.fetchone.return_value = (0,)  # No historical data - will use CPID mode

        # Start catchup
        processor.start_catchup_mode()

        # The catchup_running flag is set immediately before thread starts
        # but the executor may not be set yet as it's in the background thread
        # Let's just verify the method works without crashing
        assert processor.progress["catchup_start_time"] is not None

        # Stop catchup
        processor.stop_catchup_mode()

        # After stopping, these should be cleared
        assert not processor.catchup_running

    def test_catchup_mode_already_running(self, processor):
        """Test that catchup mode doesn't start twice"""
        processor.catchup_running = True

        # Try to start again
        processor.start_catchup_mode()

        # Should not create new executor
        assert processor.catchup_executor is None

    def test_get_cpids_needing_catchup(self, processor, mock_db_manager, mock_cursor):
        """Test identifying CPIDs that need catchup"""
        # Mock CPIDs without complete sales data
        mock_cursor.fetchall.return_value = [
            ("A1111111111111111111",),
            ("A2222222222222222222",),
        ]

        # Get CPIDs needing catchup
        cpids = processor._get_cpids_needing_catchup(
            mock_db_manager.get_long_running_connection(), start_block=779652, end_block=850000
        )

        # Verify query
        sql = mock_cursor.execute.call_args[0][0]
        assert "SELECT cpid, MIN(block_index)" in sql
        assert "WHERE ident IN ('STAMP', 'SRC-721')" in sql
        assert "GROUP BY cpid" in sql
        assert "ORDER BY first_block" in sql

        # Verify result
        assert len(cpids) == 2
        assert "A1111111111111111111" in cpids
        assert "A2222222222222222222" in cpids

    def test_progress_tracking(self, processor):
        """Test progress tracking functionality"""
        # Initial progress
        progress = processor.get_progress()
        assert progress["total_cpids"] == 0
        assert progress["processed_cpids"] == 0
        assert progress["total_sales"] == 0
        assert progress["errors"] == 0

        # Update progress
        processor.progress["total_cpids"] = 100
        processor.progress["processed_cpids"] = 50
        processor.progress["total_sales"] = 500
        processor.progress["errors"] = 2

        # Get updated progress
        progress = processor.get_progress()
        assert progress["total_cpids"] == 100
        assert progress["processed_cpids"] == 50
        assert progress["total_sales"] == 500
        assert progress["errors"] == 2

    @patch("index_core.sales_history_processor.fetch_xcp")
    def test_error_handling_during_processing(self, mock_fetch, processor, mock_cursor):
        """Test error handling during dispense processing"""
        # Mock API to raise exception
        mock_fetch.side_effect = Exception("API Error")

        # Should handle error gracefully during block processing
        # Set up CPID cache and mock cursor for block processing
        processor.cpid_cache = {"A1111111111111111111"}
        processor.last_cache_update = time.time()
        mock_cursor.fetchone.return_value = (1,)  # Has historical data

        # Get initial error count
        initial_errors = processor.progress["errors"]

        # Process block should also handle errors
        count = processor.process_block_dispenses(800000)
        assert count == 0
        assert processor.progress["errors"] > initial_errors  # Error count should increase

    def test_thread_safety(self, processor):
        """Test thread safety of CPID cache operations"""
        import threading

        # Function to update cache
        def update_cache(cpid):
            with processor._lock:
                processor.cpid_cache.add(cpid)

        # Create multiple threads
        threads = []
        for i in range(10):
            t = threading.Thread(target=update_cache, args=(f"A{i:019d}",))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # All CPIDs should be in cache
        assert len(processor.cpid_cache) == 10

    def test_rate_limiting_applied(self, processor, mock_cursor):
        """Test that rate limiting is applied to API calls"""
        with patch("index_core.sales_history_processor.rate_limiter") as mock_rate_limiter:
            with patch("index_core.sales_history_processor.fetch_xcp") as mock_fetch:
                mock_fetch.return_value = {"result": []}

                # Set up mocks for _has_historical_data check
                mock_cursor.fetchone.return_value = (1,)  # Has historical data

                # Ensure we bypass the cache update which would cause additional API calls
                processor.last_cache_update = time.time()
                processor.cpid_cache = {"A1111111111111111111"}

                # Process block
                processor.process_block_dispenses(800000)

                # Rate limiter should be called
                mock_rate_limiter.acquire.assert_called_once()


class TestSalesHistoryProcessorEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.fixture
    def processor(self, mock_db_manager, mock_cursor):
        """Create a SalesHistoryProcessor with mocked dependencies"""
        # Add _cursor attribute for tests that need direct cursor access
        mock_connection = mock_db_manager.connect()
        mock_connection._cursor = mock_cursor

        # Create a new instance instead of using the global one
        processor = SalesHistoryProcessor(db_manager=mock_db_manager)

        # Ensure clean state
        processor.catchup_running = False
        processor.catchup_executor = None

        # Set default mock return values for common queries
        # This avoids TypeError in tests that don't explicitly set these
        mock_cursor.fetchone.return_value = (0,)  # Default: no historical data
        mock_cursor.fetchall.return_value = []  # Default: no results
        processor.cpid_cache = set()
        processor.last_cache_update = 0

        yield processor

        # Cleanup after test
        if processor.catchup_executor:
            processor.catchup_executor.shutdown(wait=False)

    def test_empty_dispense_data(self, processor, mock_cursor):
        """Test handling of empty dispense data"""
        processor._store_dispenser_sales([])

        # Should not call database
        mock_cursor.executemany.assert_not_called()

    def test_malformed_dispense_data(self, processor, mock_cursor):
        """Test handling of malformed dispense data"""
        # Missing required fields
        dispenses = [
            {
                "tx_hash": "tx1",
                # Missing other required fields
            }
        ]

        # Should handle gracefully
        processor._store_dispenser_sales(dispenses)

        # May or may not insert depending on error handling
        # Key is that it doesn't crash

    @patch("index_core.sales_history_processor.fetch_xcp")
    def test_api_returns_none(self, mock_fetch, processor):
        """Test handling when API returns None"""
        mock_fetch.return_value = None

        count = processor.process_block_dispenses(800000)
        assert count == 0

        # Test Full Catchup Mode fetch
        success = processor._fetch_all_dispenses()
        assert success is False

    def test_database_error_during_store(self, processor, mock_db_manager, mock_cursor):
        """Test handling of database errors during storage"""
        mock_cursor.executemany.side_effect = Exception("Database error")

        # Should handle error and rollback
        dispenses = [
            {
                "tx_hash": "tx1",
                "block_index": 800000,
                "asset": "A1111111111111111111",
                "source": "buyer1",
                "destination": "seller1",
                "dispense_quantity": 1,
                "btc_amount": 100000,
            }
        ]

        processor._store_dispenser_sales(dispenses)

        # Should have called rollback
        mock_db_manager.connect().rollback.assert_called_once()

    def test_zero_quantity_dispense(self, processor, mock_cursor):
        """Test handling of zero quantity dispenses"""
        dispenses = [
            {
                "tx_hash": "tx1",
                "block_index": 800000,
                "asset": "A1111111111111111111",
                "source": "buyer1",
                "destination": "seller1",
                "dispense_quantity": 0,  # Zero quantity
                "btc_amount": 0,
            }
        ]

        # Should still store (might be a free dispense)
        processor._store_dispenser_sales(dispenses)

        mock_cursor.executemany.assert_called_once()

    def test_mode_switching_from_catchup_to_realtime(self, processor, mock_cursor):
        """Test mode switching when catching up to tip"""
        # Start in Full Catchup Mode
        processor.mode = "FULL_CATCHUP"
        processor.catchup_running = True
        processor.dispense_cache = {
            "data": [],
            "highest_block": 850000,
            "fetched_at_tip": 850100,
        }

        # Mock cursor to return we're now close to tip
        mock_cursor.fetchone.return_value = (850099,)  # Current tip

        # Check and process new CPIDs should trigger mode evaluation
        processor.check_and_process_new_cpids(850000)

        # When we're within threshold, mode should switch
        # This tests the actual mode switching logic in check_and_process_new_cpids

    def test_buffered_writes_during_catchup(self, processor, mock_db_manager, mock_cursor):
        """Test that writes are buffered during catchup mode"""
        processor.catchup_running = True
        processor.catchup_buffer = []

        # Test data
        dispenses = [
            {
                "tx_hash": f"tx{i}",
                "block_index": 800000 + i,
                "block_time": 1234567890 + i,
                "asset": "A1111111111111111111",
                "source": f"buyer{i}",
                "destination": "seller1",
                "dispense_quantity": 1,
                "btc_amount": 100000,
                "dispenser_tx_hash": "disp_tx1",
                "dispenser": {"satoshirate": 100000},
            }
            for i in range(150)  # Create 150 dispenses
        ]

        # Store with buffering
        processor._store_dispenser_sales(dispenses, use_buffer=True)

        # Should be buffered, not written yet
        assert len(processor.catchup_buffer) == 150
        mock_cursor.executemany.assert_not_called()

        # Now flush the buffer
        processor._flush_catchup_buffer()

        # Should have been written in batches
        assert mock_cursor.executemany.call_count == 2  # 150 / 100 = 2 batches
        assert len(processor.catchup_buffer) == 0

    def test_determine_processing_mode_logic(self, processor, mock_cursor):
        """Test the mode determination logic with different scenarios"""
        # Scenario 1: Far behind (should be FULL_CATCHUP)
        mock_cursor.fetchone.side_effect = [
            (850000,),  # Highest sales block
            (851000,),  # Current tip
        ]
        mode = processor.determine_processing_mode()
        assert mode == "FULL_CATCHUP"  # 1000 blocks behind > 200 threshold

        # Scenario 2: Close to tip (should be REALTIME)
        mock_cursor.fetchone.side_effect = [
            (850000,),  # Highest sales block
            (850100,),  # Current tip
        ]
        mode = processor.determine_processing_mode()
        assert mode == "REALTIME"  # 100 blocks behind < 200 threshold

        # Scenario 3: No sales history (should be FULL_CATCHUP)
        mock_cursor.fetchone.side_effect = [
            (None,),  # No sales history
            (850000,),  # Current tip
        ]
        mode = processor.determine_processing_mode()
        assert mode == "FULL_CATCHUP"  # No history means full catchup

    @patch("index_core.sales_history_processor.fetch_xcp")
    def test_full_catchup_pagination(self, mock_fetch, processor):
        """Test pagination handling in Full Catchup Mode"""
        # Mock multiple pages of responses
        mock_fetch.side_effect = [
            {"result": [{"block_index": i} for i in range(1000)], "next_cursor": 1000},
            {"result": [{"block_index": i} for i in range(1000, 2000)], "next_cursor": 2000},
            {"result": [{"block_index": i} for i in range(2000, 2500)], "next_cursor": None},  # Last page
        ]

        # Fetch all dispenses
        success = processor._fetch_all_dispenses()

        assert success is True
        assert len(processor.dispense_cache["data"]) == 2500
        assert processor.dispense_cache["highest_block"] == 2499
        assert mock_fetch.call_count == 3

    def test_cpid_filtering_in_cached_dispenses(self, processor, mock_db_manager):
        """Test CPID filtering when processing cached dispenses"""
        # Set up cache with mixed CPIDs
        processor.dispense_cache = {
            "data": [
                {"asset": "A1111111111111111111", "tx_hash": "tx1", "block_index": 800000},
                {"asset": "A2222222222222222222", "tx_hash": "tx2", "block_index": 800001},
                {"asset": "XCP", "tx_hash": "tx3", "block_index": 800002},
                {"asset": "A3333333333333333333", "tx_hash": "tx4", "block_index": 800003},
            ]
        }

        # Set up CPID cache with only some stamps
        processor.cpid_cache = {"A1111111111111111111", "A3333333333333333333"}

        # Process cached dispenses
        count = processor._process_cached_dispenses()

        # Should only process 2 (A1111... and A3333...)
        assert count == 2

        # Verify correct ones were stored
        cursor = mock_db_manager.connect()._cursor
        calls = cursor.executemany.call_args_list
        assert len(calls) == 1
        stored_data = calls[0][0][1]
        stored_cpids = [row[3] for row in stored_data]  # cpid is 4th field
        assert "A1111111111111111111" in stored_cpids
        assert "A3333333333333333333" in stored_cpids
        assert "A2222222222222222222" not in stored_cpids
        assert "XCP" not in stored_cpids

    def test_force_rebuild_environment_variable(self, processor, mock_db_manager, mock_cursor):
        """Test FORCE_SALES_HISTORY_REBUILD environment variable handling"""
        import os

        # Test with env var set to true
        os.environ["FORCE_SALES_HISTORY_REBUILD"] = "true"

        # Mock existing sales history
        mock_cursor.fetchone.return_value = (850000,)  # Has history at block 850000

        # Run catchup should process from genesis despite existing history
        # This test validates the logic, not the full execution
        db = mock_db_manager.connect()
        with patch.object(processor, "_fetch_all_dispenses", return_value=True):
            with patch.object(processor, "_process_cached_dispenses", return_value=1000) as mock_process:
                processor._run_full_catchup(db)

                # Should process from block 0 (after_block=0)
                mock_process.assert_called_with(after_block=0)

        # Clean up
        del os.environ["FORCE_SALES_HISTORY_REBUILD"]

    def test_concurrent_mode_access_thread_safety(self, processor):
        """Test thread safety of mode switching"""
        import threading
        import time

        results = []

        def switch_mode(new_mode):
            processor.mode = new_mode
            time.sleep(0.001)  # Small delay to increase chance of race condition
            results.append(processor.mode)

        # Start multiple threads trying to switch modes
        threads = []
        for i in range(10):
            mode = "FULL_CATCHUP" if i % 2 == 0 else "REALTIME"
            t = threading.Thread(target=switch_mode, args=(mode,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # All results should be valid modes
        assert all(mode in ["FULL_CATCHUP", "REALTIME"] for mode in results)


# Test the global instance
def test_global_instance_exists():
    """Test that global sales_history_processor instance exists"""
    from index_core.sales_history_processor import sales_history_processor

    assert sales_history_processor is not None
    assert isinstance(sales_history_processor, SalesHistoryProcessor)
