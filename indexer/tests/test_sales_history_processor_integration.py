"""
Integration tests for SalesHistoryProcessor

These tests validate the actual Counterparty API interactions and data flow.
They require network access and should not run in CI.

Run with: poetry run pytest tests/test_sales_history_processor_integration.py -v -m integration
"""

import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from index_core.database_manager import DatabaseManager
from index_core.fetch_utils import fetch_xcp
from index_core.sales_history_processor import SalesHistoryProcessor

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.mark.integration
class TestSalesHistoryProcessorIntegration:
    """Integration tests for SalesHistoryProcessor that validate Counterparty API interactions"""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Cleanup any global state before and after each test"""
        # Run test
        yield

        # Cleanup after test - reset global instance state
        from index_core.sales_history_processor import sales_history_processor

        if hasattr(sales_history_processor, "catchup_running"):
            sales_history_processor.catchup_running = False
        if hasattr(sales_history_processor, "catchup_executor") and sales_history_processor.catchup_executor:
            sales_history_processor.catchup_executor.shutdown(wait=False)
            sales_history_processor.catchup_executor = None
        if hasattr(sales_history_processor, "cpid_cache"):
            sales_history_processor.cpid_cache.clear()
        if hasattr(sales_history_processor, "last_cache_update"):
            sales_history_processor.last_cache_update = 0

    @pytest.fixture
    def processor(self):
        """Create a fresh processor instance for testing"""
        # Use a mock database manager for integration tests
        mock_db_manager = Mock(spec=DatabaseManager)
        mock_db = MagicMock()
        mock_cursor = MagicMock()

        # Setup mock database connection
        mock_db_manager.connect.return_value = mock_db
        mock_db_manager.get_long_running_connection.return_value = mock_db
        mock_db.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_db.cursor.return_value.__exit__ = lambda self, *args: None

        # Return empty results by default
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = None

        # Create fresh instance with clean state
        processor = SalesHistoryProcessor(db_manager=mock_db_manager)
        processor.catchup_running = False
        processor.catchup_executor = None
        processor.cpid_cache = set()
        processor.last_cache_update = 0
        processor._test_mode = True  # Add test mode flag if needed

        yield processor

        # Cleanup
        if processor.catchup_executor:
            processor.catchup_executor.shutdown(wait=False)

    def test_counterparty_api_dispenser_fetch(self, processor):
        """Test fetching dispensers from Counterparty API"""
        # Test with a known CPID that has dispensers
        test_cpid = "A1111111111111111111"  # Replace with actual CPID if needed

        # Mock the CPID cache to include our test CPID
        processor.cpid_cache = {test_cpid}
        processor.last_cache_update = time.time()

        # Test fetching dispensers
        dispensers_count = processor._process_single_cpid_dispenses(test_cpid)

        # Verify the API was called correctly
        assert isinstance(dispensers_count, int)
        assert dispensers_count >= 0

    def test_counterparty_api_dispense_fetch(self):
        """Test fetching dispenses from Counterparty API directly"""
        # Test the actual API endpoint
        response = fetch_xcp("/blocks/800000/dispenses", {"verbose": "true", "show_unconfirmed": "false"})

        # Validate response structure
        assert response is not None
        assert "result" in response
        assert isinstance(response["result"], list)

        # If there are dispenses, validate their structure
        if response["result"]:
            dispense = response["result"][0]
            # Check required fields exist
            assert "tx_hash" in dispense
            assert "block_index" in dispense
            assert "asset" in dispense
            assert "source" in dispense
            assert "destination" in dispense

    def test_cpid_cache_update(self, processor):
        """Test CPID cache update from database"""
        # Mock database to return some CPIDs
        mock_cursor = processor.db_manager.connect().cursor().__enter__()
        mock_cursor.fetchall.return_value = [
            ("A1111111111111111111",),
            ("A2222222222222222222",),
            ("A3333333333333333333",),
        ]

        # Clear cache to force update
        processor.last_cache_update = 0
        processor.update_cpid_cache()

        # Verify cache was updated
        assert len(processor.cpid_cache) == 3
        assert "A1111111111111111111" in processor.cpid_cache
        assert processor.last_cache_update > 0

    def test_process_block_dispenses_filtering(self, processor):
        """Test that block dispense processing filters by CPID correctly"""
        # Set up CPID cache with specific CPIDs
        processor.cpid_cache = {"A1111111111111111111", "A2222222222222222222"}
        processor.last_cache_update = time.time()

        # Mock the API response with mixed CPIDs
        with patch("index_core.sales_history_processor.fetch_xcp") as mock_fetch:
            mock_fetch.return_value = {
                "result": [
                    {
                        "tx_hash": "tx1",
                        "block_index": 800000,
                        "asset": "A1111111111111111111",  # Should be included
                        "source": "buyer1",
                        "destination": "dispenser1",
                        "dispense_quantity": 1,
                        "btc_amount": 100000,
                        "dispenser": {"satoshirate": 100000},
                    },
                    {
                        "tx_hash": "tx2",
                        "block_index": 800000,
                        "asset": "XCP",  # Should be filtered out
                        "source": "buyer2",
                        "destination": "dispenser2",
                        "dispense_quantity": 1,
                        "btc_amount": 200000,
                        "dispenser": {"satoshirate": 200000},
                    },
                    {
                        "tx_hash": "tx3",
                        "block_index": 800000,
                        "asset": "A2222222222222222222",  # Should be included
                        "source": "buyer3",
                        "destination": "dispenser3",
                        "dispense_quantity": 1,
                        "btc_amount": 300000,
                        "dispenser": {"satoshirate": 300000},
                    },
                ]
            }

            # Process the block
            count = processor.process_block_dispenses(800000)

            # Should only process stamp CPIDs
            assert count == 2

    def test_volume_calculation_accuracy(self, processor):
        """Test volume calculation from stored data"""
        # Mock the database to return sales data
        mock_cursor = processor.db_manager.connect().cursor().__enter__()

        # Mock data for 24h volume calculation
        current_time = int(time.time())
        mock_cursor.fetchone.return_value = (
            10000000,  # total_volume_sats (0.1 BTC)
            5,  # trade_count
            200000,  # high_price
            100000,  # low_price
            current_time - 3600,  # last_sale_time (1 hour ago)
        )

        # Calculate volume
        volume_data = processor.calculate_volume_from_history("A1111111111111111111", hours=24)

        # Verify calculations
        assert volume_data["volume_btc"] == 0.1  # 10000000 sats = 0.1 BTC
        assert volume_data["trade_count"] == 5
        assert volume_data["high_sats"] == 200000
        assert volume_data["low_sats"] == 100000
        assert volume_data["last_sale_time"] == current_time - 3600

    def test_rate_limiting(self, processor):
        """Test that rate limiting is applied to API calls"""
        import time

        from index_core.sales_history_processor import rate_limiter

        # Reset rate limiter
        rate_limiter.last_call = 0

        # Make multiple rapid calls
        start_time = time.time()
        for i in range(3):
            rate_limiter.acquire()
        end_time = time.time()

        # Should take at least 1 second for 3 calls at 2 calls/second
        elapsed = end_time - start_time
        assert elapsed >= 1.0, f"Rate limiting not working correctly, elapsed: {elapsed}"

    def test_error_handling_api_failure(self, processor):
        """Test graceful handling of API failures"""
        with patch("index_core.sales_history_processor.fetch_xcp") as mock_fetch:
            # Simulate API failure
            mock_fetch.return_value = None

            # Should handle gracefully and return 0
            count = processor.process_block_dispenses(800000)
            assert count == 0

            # Simulate API returning error structure
            mock_fetch.return_value = {"error": "API Error"}
            count = processor.process_block_dispenses(800001)
            assert count == 0

    def test_catchup_mode_cpid_detection(self, processor):
        """Test that catchup mode correctly identifies CPIDs needing processing"""
        mock_cursor = processor.db_manager.get_long_running_connection().cursor().__enter__()

        # Mock CPIDs that need catchup (no sales history)
        mock_cursor.fetchall.return_value = [
            ("A1111111111111111111",),
            ("A2222222222222222222",),
        ]

        # Get CPIDs needing catchup
        cpids = processor._get_cpids_needing_catchup(
            processor.db_manager.get_long_running_connection(), start_block=779652, end_block=None
        )

        assert len(cpids) == 2
        assert "A1111111111111111111" in cpids
        assert "A2222222222222222222" in cpids

    @pytest.mark.skip(reason="Long running test - enable for thorough testing")
    def test_catchup_mode_execution(self, processor):
        """Test full catchup mode execution (WARNING: This may take time)"""
        # This test actually runs catchup mode - skip by default
        processor.start_catchup_mode(start_block=800000, end_block=800010)  # Limit to 10 blocks for testing

        # Wait a bit for background thread to start
        time.sleep(2)

        # Check progress
        progress = processor.get_progress()
        assert progress["catchup_start_time"] is not None
        assert progress["total_cpids"] >= 0

        # Stop catchup
        processor.stop_catchup_mode()
        assert not processor.catchup_running

    def test_dispense_data_parsing(self, processor):
        """Test correct parsing of dispense data from API response"""
        # Mock a dispense response with nested dispenser data
        test_dispense = {
            "tx_hash": "abc123",
            "block_index": 800000,
            "block_time": 1234567890,
            "asset": "A1111111111111111111",
            "source": "buyer_address",  # Buyer
            "destination": "dispenser_address",  # Dispenser
            "dispense_quantity": 5,
            "btc_amount": 500000,  # Already in satoshis
            "dispenser_tx_hash": "dispenser_tx_123",
            "dispenser": {"satoshirate": 100000, "status": 0},  # Price per unit  # Active
        }

        # Process this dispense data
        with patch.object(processor.db_manager, "connect") as mock_connect:
            mock_db = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value = mock_db
            mock_db.cursor.return_value.__enter__ = lambda self: mock_cursor
            mock_db.cursor.return_value.__exit__ = lambda self, *args: None

            # Store the dispense
            processor._store_dispenser_sales([test_dispense])

            # Verify the data was parsed correctly
            mock_cursor.executemany.assert_called_once()
            call_args = mock_cursor.executemany.call_args[0]
            insert_data = call_args[1][0]  # First row of data

            # Verify field mapping
            assert insert_data[0] == "abc123"  # tx_hash
            assert insert_data[1] == 800000  # block_index
            assert insert_data[2] == 1234567890  # block_time
            assert insert_data[3] == "A1111111111111111111"  # cpid
            assert insert_data[5] == "buyer_address"  # buyer_address
            assert insert_data[6] == "dispenser_address"  # seller_address
            assert insert_data[7] == 5  # quantity
            assert insert_data[8] == 500000  # btc_amount
            assert insert_data[9] == 100000  # unit_price_sats
            assert insert_data[10] == "dispenser_tx_123"  # dispenser_tx_hash


@pytest.mark.integration
class TestMarketDataIntegration:
    """Test integration between sales history and market data"""

    def test_stamp_worker_uses_sales_history(self):
        """Test that stamp_worker correctly queries sales history instead of API"""
        from index_core.stamp_worker import StampWorker

        worker = StampWorker()

        # Mock the sales history processor
        with patch("index_core.stamp_worker.sales_history_processor") as mock_processor:
            # Setup mock return values
            mock_processor.calculate_volume_from_history.return_value = {
                "volume_btc": 0.5,
                "trade_count": 10,
                "high_sats": 200000,
                "low_sats": 100000,
                "last_sale_time": int(time.time()),
            }

            mock_processor.get_recent_sales.return_value = [
                {
                    "tx_hash": "test_tx",
                    "block_index": 800000,
                    "block_time": int(time.time()),
                    "unit_price_sats": 150000,
                    "buyer_address": "buyer1",
                    "seller_address": "seller1",
                    "btc_amount": 150000,
                    "dispenser_tx_hash": "disp_tx",
                }
            ]

            # Calculate volume metrics
            result = worker._calculate_volume_metrics_from_history("A1111111111111111111")

            # Verify it called the sales history processor
            mock_processor.calculate_volume_from_history.assert_called()
            mock_processor.get_recent_sales.assert_called_with(limit=1, cpid="A1111111111111111111")

            # Verify the result structure
            assert result["volume_24h_btc"] == 0.5
            assert result["total_dispenses_count"] == 10
            assert result["last_sale_tx_hash"] == "test_tx"
            assert result["last_sale_buyer_address"] == "buyer1"


@pytest.mark.integration
class TestAutomaticCatchupMode:
    """Test automatic catchup mode behavior"""

    @pytest.fixture
    def processor(self):
        """Create a fresh processor instance for testing"""
        # Use a mock database manager for integration tests
        mock_db_manager = Mock(spec=DatabaseManager)
        mock_db = MagicMock()
        mock_cursor = MagicMock()

        # Setup mock database connection
        mock_db_manager.connect.return_value = mock_db
        mock_db_manager.get_long_running_connection.return_value = mock_db
        mock_db.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_db.cursor.return_value.__exit__ = lambda self, *args: None

        # Create fresh instance with clean state
        processor = SalesHistoryProcessor(db_manager=mock_db_manager)
        processor.catchup_running = False
        processor.catchup_executor = None
        processor.cpid_cache = set()
        processor.last_cache_update = 0

        yield processor

        # Cleanup
        if processor.catchup_executor:
            processor.catchup_executor.shutdown(wait=False)

    def test_catchup_starts_when_data_missing(self, processor):
        """Test that catchup mode starts automatically when sales data is missing"""
        # Mock database to indicate missing sales data
        mock_cursor = processor.db_manager.get_long_running_connection().cursor().__enter__()
        mock_cursor.fetchall.return_value = [
            ("A1111111111111111111",),  # CPIDs needing catchup
        ]

        # Simulate what should happen in market_data_jobs.py
        cpids_needing_catchup = processor._get_cpids_needing_catchup(
            processor.db_manager.get_long_running_connection(), start_block=779652, end_block=None
        )

        # Should detect CPIDs needing catchup
        assert len(cpids_needing_catchup) > 0

        # In real implementation, market_data_jobs.py would:
        # if cpids_needing_catchup:
        #     processor.start_catchup_mode()

    def test_no_catchup_when_data_exists(self, processor):
        """Test that catchup mode doesn't start when data already exists"""
        # Mock database to indicate all CPIDs have sales data
        mock_cursor = processor.db_manager.get_long_running_connection().cursor().__enter__()
        mock_cursor.fetchall.return_value = []  # No CPIDs need catchup

        cpids_needing_catchup = processor._get_cpids_needing_catchup(
            processor.db_manager.get_long_running_connection(), start_block=779652, end_block=None
        )

        # Should not need catchup
        assert len(cpids_needing_catchup) == 0


# Performance tests that can be run separately
@pytest.mark.slow
@pytest.mark.integration
class TestPerformance:
    """Performance tests for CPID filtering and processing"""

    @pytest.fixture
    def processor(self):
        """Create a fresh processor instance for testing"""
        # Use a mock database manager for integration tests
        mock_db_manager = Mock(spec=DatabaseManager)

        # Create fresh instance with clean state
        processor = SalesHistoryProcessor(db_manager=mock_db_manager)
        processor.catchup_running = False
        processor.catchup_executor = None
        processor.cpid_cache = set()
        processor.last_cache_update = 0

        yield processor

        # Cleanup
        if processor.catchup_executor:
            processor.catchup_executor.shutdown(wait=False)

    def test_cpid_cache_performance(self, processor):
        """Test performance of CPID cache with large dataset"""
        # Create a large CPID set
        large_cpid_set = {f"A{i:019d}" for i in range(10000)}
        processor.cpid_cache = large_cpid_set
        processor.last_cache_update = time.time()

        # Time lookups
        start_time = time.time()
        for i in range(1000):
            test_cpid = f"A{i:019d}"
            _ = test_cpid in processor.cpid_cache
        end_time = time.time()

        # Should be very fast (< 0.01 seconds for 1000 lookups)
        elapsed = end_time - start_time
        assert elapsed < 0.01, f"CPID cache lookups too slow: {elapsed} seconds"

    def test_batch_processing_performance(self, processor):
        """Test performance of batch processing"""
        # Mock a batch of CPIDs
        batch_cpids = [f"A{i:019d}" for i in range(100)]

        # Initialize the catchup executor for batch processing
        from concurrent.futures import ThreadPoolExecutor

        processor.catchup_executor = ThreadPoolExecutor(max_workers=5)
        processor.catchup_running = True

        try:
            # Mock the processing to be fast
            with patch.object(processor, "_process_single_cpid_dispenses") as mock_process:
                mock_process.return_value = 5  # Each CPID has 5 dispenses

                start_time = time.time()
                processor._process_cpid_batch(batch_cpids, Mock())
                end_time = time.time()

                # Should process 100 CPIDs quickly
                elapsed = end_time - start_time
                assert elapsed < 5.0, f"Batch processing too slow: {elapsed} seconds"

                # Verify all CPIDs were processed
                assert mock_process.call_count == 100
        finally:
            # Clean up executor
            if processor.catchup_executor:
                processor.catchup_executor.shutdown(wait=False)
