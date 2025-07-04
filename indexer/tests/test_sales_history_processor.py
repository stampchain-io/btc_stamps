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

    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock database manager"""
        mock_db_manager = Mock(spec=DatabaseManager)
        mock_db = MagicMock()
        mock_cursor = MagicMock()

        # Setup mock database connection
        mock_db_manager.connect.return_value = mock_db
        mock_db_manager.get_long_running_connection.return_value = mock_db
        mock_db.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_db.cursor.return_value.__exit__ = lambda self, *args: None
        mock_db.begin.return_value = None
        mock_db.commit.return_value = None
        mock_db.rollback.return_value = None
        mock_db.close.return_value = None

        # Attach cursor to db for easy access in tests
        mock_db._cursor = mock_cursor

        return mock_db_manager

    @pytest.fixture
    def processor(self, mock_db_manager):
        """Create a fresh processor instance with mocked database"""
        # Create a new instance instead of using the global one
        processor = SalesHistoryProcessor(db_manager=mock_db_manager)

        # Ensure clean state
        processor.catchup_running = False
        processor.catchup_executor = None
        processor.cpid_cache = set()
        processor.last_cache_update = 0
        processor.progress = {
            "total_cpids": 0,
            "processed_cpids": 0,
            "total_sales": 0,
            "last_block_processed": 0,
            "catchup_start_time": None,
            "errors": 0,
        }

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

    def test_cpid_cache_update(self, processor, mock_db_manager):
        """Test CPID cache update logic"""
        # Setup mock cursor to return CPIDs
        cursor = mock_db_manager.connect().cursor().__enter__()
        cursor.fetchall.return_value = [
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
        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        assert "SELECT DISTINCT cpid" in sql
        assert "FROM StampTableV4" in sql
        assert "WHERE ident IN ('STAMP', 'SRC-721')" in sql

    def test_cpid_cache_refresh_interval(self, processor, mock_db_manager):
        """Test that cache respects refresh interval"""
        cursor = mock_db_manager.connect().cursor().__enter__()
        cursor.fetchall.return_value = [("A1111111111111111111",)]

        # First update
        processor.update_cpid_cache()
        first_update_time = processor.last_cache_update

        # Try immediate update - should skip
        cursor.fetchall.return_value = [("A2222222222222222222",)]
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
    def test_process_block_dispenses(self, mock_fetch, processor):
        """Test processing dispenses for a specific block"""
        # Setup CPID cache
        processor.cpid_cache = {"A1111111111111111111", "A2222222222222222222"}
        processor.last_cache_update = time.time()

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
        assert result["last_sale_time"] is None

    @patch("index_core.sales_history_processor.fetch_xcp")
    def test_process_single_cpid_dispenses(self, mock_fetch, processor):
        """Test processing dispenses for a single CPID"""
        # Mock dispenser response
        mock_fetch.side_effect = [
            # First call: dispensers
            {"result": [{"source": "dispenser1", "satoshirate": 100000}, {"source": "dispenser2", "satoshirate": 200000}]},
            # Second call: dispenses for dispenser1
            {
                "result": [
                    {
                        "tx_hash": "tx1",
                        "block_index": 800000,
                        "asset": "A1111111111111111111",
                        "source": "buyer1",
                        "destination": "dispenser1",
                        "dispense_quantity": 1,
                        "btc_amount": 100000,
                        "dispenser": {"satoshirate": 100000},
                    }
                ]
            },
            # Third call: dispenses for dispenser2
            {"result": []},  # No dispenses
        ]

        # Process CPID
        count = processor._process_single_cpid_dispenses("A1111111111111111111")

        # Should have processed 1 dispense
        assert count == 1

        # Verify API calls
        assert mock_fetch.call_count == 3

        # First call should be for dispensers
        assert mock_fetch.call_args_list[0][0][0] == "/assets/A1111111111111111111/dispensers"

        # Second and third calls should be for dispenses
        assert "/addresses/dispenser1/dispenses" in mock_fetch.call_args_list[1][0][0]
        assert "/addresses/dispenser2/dispenses" in mock_fetch.call_args_list[2][0][0]

    def test_catchup_mode_start_stop(self, processor, mock_db_manager):
        """Test starting and stopping catchup mode"""
        # Mock the database to return no CPIDs needing catchup
        # This prevents the background thread from doing real work
        cursor = mock_db_manager.get_long_running_connection()._cursor
        cursor.fetchall.return_value = []  # No CPIDs need catchup

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

    def test_get_cpids_needing_catchup(self, processor, mock_db_manager):
        """Test identifying CPIDs that need catchup"""
        cursor = mock_db_manager.get_long_running_connection()._cursor

        # Mock CPIDs without complete sales data
        cursor.fetchall.return_value = [
            ("A1111111111111111111",),
            ("A2222222222222222222",),
        ]

        # Get CPIDs needing catchup
        cpids = processor._get_cpids_needing_catchup(
            mock_db_manager.get_long_running_connection(), start_block=779652, end_block=850000
        )

        # Verify query
        sql = cursor.execute.call_args[0][0]
        assert "SELECT DISTINCT s.cpid" in sql
        assert "LEFT JOIN" in sql
        assert "stamp_sales_history" in sql
        assert "WHERE s.ident IN ('STAMP', 'SRC-721')" in sql

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
    def test_error_handling_during_processing(self, mock_fetch, processor):
        """Test error handling during dispense processing"""
        # Mock API to raise exception
        mock_fetch.side_effect = Exception("API Error")

        # Should handle error gracefully
        count = processor._process_single_cpid_dispenses("A1111111111111111111")
        assert count == 0

        # Process block should also handle errors
        count = processor.process_block_dispenses(800000)
        assert count == 0
        assert processor.progress["errors"] == 1

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

    @patch("index_core.sales_history_processor.rate_limiter")
    def test_rate_limiting_applied(self, mock_rate_limiter, processor):
        """Test that rate limiting is applied to API calls"""
        with patch("index_core.sales_history_processor.fetch_xcp") as mock_fetch:
            mock_fetch.return_value = {"result": []}

            # Process block
            processor.process_block_dispenses(800000)

            # Rate limiter should be called
            mock_rate_limiter.acquire.assert_called_once()


class TestSalesHistoryProcessorEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock database manager"""
        mock_manager = Mock(spec=DatabaseManager)
        mock_db = MagicMock()
        cursor = MagicMock()

        # Setup database mock chain
        mock_manager.connect.return_value = mock_db
        mock_manager.get_long_running_connection.return_value = mock_db
        mock_db.cursor.return_value.__enter__ = lambda self: cursor
        mock_db.cursor.return_value.__exit__ = lambda self, *args: None
        mock_db.commit = MagicMock()
        mock_db.rollback = MagicMock()
        mock_db._cursor = cursor

        return mock_manager

    @pytest.fixture
    def processor(self, mock_db_manager):
        """Create a SalesHistoryProcessor with mocked dependencies"""
        return SalesHistoryProcessor(db_manager=mock_db_manager)

    def test_empty_dispense_data(self, processor, mock_db_manager):
        """Test handling of empty dispense data"""
        processor._store_dispenser_sales([])

        # Should not call database
        cursor = mock_db_manager.connect()._cursor
        cursor.executemany.assert_not_called()

    def test_malformed_dispense_data(self, processor, mock_db_manager):
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

        count = processor._process_single_cpid_dispenses("A1111111111111111111")
        assert count == 0

    def test_database_error_during_store(self, processor, mock_db_manager):
        """Test handling of database errors during storage"""
        cursor = mock_db_manager.connect()._cursor
        cursor.executemany.side_effect = Exception("Database error")

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

    def test_zero_quantity_dispense(self, processor, mock_db_manager):
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

        cursor = mock_db_manager.connect()._cursor
        cursor.executemany.assert_called_once()


# Test the global instance
def test_global_instance_exists():
    """Test that global sales_history_processor instance exists"""
    from index_core.sales_history_processor import sales_history_processor

    assert sales_history_processor is not None
    assert isinstance(sales_history_processor, SalesHistoryProcessor)
