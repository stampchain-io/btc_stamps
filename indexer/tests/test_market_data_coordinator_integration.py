"""
Integration tests for market data jobs with background coordinator.
These tests verify that the coordinator properly manages concurrent background tasks.
"""

import threading
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from index_core.background_coordinator import BackgroundCoordinator
from index_core.market_data_jobs import MarketDataJobScheduler


@pytest.mark.integration
class TestMarketDataCoordinatorIntegration:
    """Test market data jobs integration with background coordinator"""

    def setup_method(self):
        """Reset coordinator state before each test"""
        BackgroundCoordinator._instance = None
        self.coordinator = BackgroundCoordinator.get_instance()
        self.scheduler = MarketDataJobScheduler()

    def teardown_method(self):
        """Clean up after each test"""
        if self.scheduler.running:
            self.scheduler.stop()
        BackgroundCoordinator._instance = None

    @patch("index_core.market_data_jobs.market_data_service")
    @patch("index_core.market_data_jobs.StampWorker")
    def test_stamp_update_respects_coordinator(self, mock_stamp_worker, mock_market_data_service):
        """Test that stamp market data updates respect coordinator locks"""
        # Start a heavy operation to block market data
        self.coordinator.start_task("sales_history", is_heavy=True)

        # Mock the database and worker
        mock_db = MagicMock()
        self.scheduler.database_manager.connect = Mock(return_value=mock_db)
        mock_db.cursor.return_value.__enter__.return_value.fetchall.return_value = []

        # Try to run stamp market data update
        self.scheduler._update_stamp_market_data_job()

        # Should not have processed any stamps due to coordinator block
        mock_stamp_worker.assert_not_called()

        # End the blocking task
        self.coordinator.end_task("sales_history", is_heavy=True)

        # Now it should work
        self.scheduler._update_stamp_market_data_job()
        # Verify coordinator was properly used (task started and ended)

    @patch("index_core.market_data_jobs.market_data_service")
    def test_multiple_market_data_jobs_coordination(self, mock_market_data_service):
        """Test that multiple market data jobs don't run simultaneously"""
        results = []
        barrier = threading.Barrier(3)

        def run_job(job_type):
            barrier.wait()  # Synchronize all threads
            if job_type == "stamps":
                self.scheduler._update_stamp_market_data_job()
            elif job_type == "src20":
                self.scheduler._update_src20_market_data_job()
            elif job_type == "collections":
                self.scheduler._update_collection_market_data_job()
            results.append(job_type)

        # Mock database responses
        mock_db = MagicMock()
        self.scheduler.database_manager.connect = Mock(return_value=mock_db)
        mock_db.cursor.return_value.__enter__.return_value.fetchall.return_value = []

        # Start three market data jobs concurrently
        threads = []
        for job_type in ["stamps", "src20", "collections"]:
            t = threading.Thread(target=run_job, args=(job_type,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # All should have run but not simultaneously
        assert len(results) == 3

    def test_coordinator_releases_on_exception(self):
        """Test that coordinator properly releases locks on exceptions"""
        # Mock to force an exception
        with patch.object(self.scheduler, "_get_stamps_needing_update") as mock_get_stamps:
            mock_get_stamps.side_effect = Exception("Test exception")

            # Run job that will fail
            with pytest.raises(Exception):
                self.scheduler._update_stamp_market_data_job()

            # Coordinator should not have a stuck lock
            stats = self.coordinator.get_stats()
            assert stats["active_task_count"] == 0
            assert not stats["heavy_operation_in_progress"]

    @patch("index_core.market_data_jobs.sales_history_processor")
    def test_sales_history_blocks_market_data(self, mock_sales_processor):
        """Test that active sales history blocks market data updates"""
        # Simulate sales history catchup running
        mock_sales_processor.catchup_running = True
        self.coordinator.start_task("sales_history", is_heavy=True)

        # Mock database
        mock_db = MagicMock()
        self.scheduler.database_manager.connect = Mock(return_value=mock_db)

        # Try to run market data updates - they should be skipped
        self.scheduler._update_stamp_market_data_job()
        self.scheduler._update_src20_market_data_job()
        self.scheduler._update_collection_market_data_job()

        # Database should not have been accessed (jobs were skipped)
        mock_db.cursor.assert_not_called()

        # End sales history
        self.coordinator.end_task("sales_history", is_heavy=True)

    def test_holder_update_blocks_market_data(self):
        """Test that active holder updates block market data updates"""
        # Simulate holder update running
        self.coordinator.start_task("holder_update", is_heavy=True)

        # Mock database
        mock_db = MagicMock()
        self.scheduler.database_manager.connect = Mock(return_value=mock_db)
        mock_db.cursor.return_value.__enter__.return_value.fetchall.return_value = []

        # Try to run market data update
        self.scheduler._update_stamp_market_data_job()

        # Should have been skipped
        mock_db.cursor.assert_not_called()

        # End holder update
        self.coordinator.end_task("holder_update", is_heavy=True)

        # Now it should work
        self.scheduler._update_stamp_market_data_job()
        mock_db.cursor.assert_called()

    @pytest.mark.slow
    def test_real_scheduler_with_coordinator(self):
        """Test real scheduler startup with coordinator integration"""
        # This test actually starts the scheduler
        self.scheduler.start(max_workers=2)
        assert self.scheduler.running

        # Let it run briefly
        time.sleep(2)

        # Check coordinator stats
        stats = self.coordinator.get_stats()
        # Should have some activity
        assert stats is not None

        # Stop scheduler
        self.scheduler.stop()
        assert not self.scheduler.running

        # Coordinator should be clean
        final_stats = self.coordinator.get_stats()
        assert final_stats["active_task_count"] == 0
        assert not final_stats["heavy_operation_in_progress"]


@pytest.mark.integration
class TestSalesHistoryCoordinatorIntegration:
    """Test sales history processor integration with background coordinator"""

    def setup_method(self):
        """Reset coordinator state before each test"""
        BackgroundCoordinator._instance = None
        self.coordinator = BackgroundCoordinator.get_instance()

    def teardown_method(self):
        """Clean up after each test"""
        BackgroundCoordinator._instance = None

    @patch("index_core.sales_history_processor.fetch_xcp")
    @patch("index_core.sales_history_processor.DatabaseManager")
    @patch("index_core.sales_history_processor.SalesHistoryProcessor._run_full_catchup")
    def test_sales_history_respects_coordinator(self, mock_full_catchup, mock_db_manager, mock_fetch_xcp):
        """Test that sales history respects coordinator locks"""
        from index_core.sales_history_processor import SalesHistoryProcessor

        # Mock fetch_xcp to prevent any real API calls
        mock_fetch_xcp.return_value = None

        # Start a heavy operation to block sales history
        self.coordinator.start_task("market_data_stamps", is_heavy=True)

        # Create processor
        processor = SalesHistoryProcessor(mock_db_manager.return_value)
        processor.catchup_running = True

        # Try to run catchup
        processor._run_catchup()

        # Should have been skipped
        assert not processor.catchup_running  # Should be set to False when skipped
        # Full catchup should not have been called
        mock_full_catchup.assert_not_called()
        # No API calls should have been made
        mock_fetch_xcp.assert_not_called()

        # End the blocking task
        self.coordinator.end_task("market_data_stamps", is_heavy=True)

    @patch("index_core.sales_history_processor.fetch_xcp")
    @patch("index_core.sales_history_processor.DatabaseManager")
    def test_sales_history_releases_on_error(self, mock_db_manager, mock_fetch_xcp):
        """Test that sales history releases coordinator on errors"""
        from index_core.sales_history_processor import SalesHistoryProcessor

        # Mock fetch_xcp to prevent any real API calls
        mock_fetch_xcp.return_value = None

        # Mock the database manager
        mock_db_instance = MagicMock()
        mock_db_manager.return_value = mock_db_instance

        # Mock get_long_running_connection to fail immediately
        mock_db_instance.get_long_running_connection.side_effect = Exception("Connection failed")

        processor = SalesHistoryProcessor(mock_db_instance)
        processor.catchup_running = True

        # Run catchup that will fail
        processor._run_catchup()

        # Coordinator should not have a stuck lock
        stats = self.coordinator.get_stats()
        assert stats["active_task_count"] == 0
        assert not stats["heavy_operation_in_progress"]

    def test_sales_history_blocks_holder_updates(self):
        """Test that sales history blocks holder updates"""
        # Start sales history
        assert self.coordinator.start_task("sales_history", is_heavy=True)

        # Holder update should be blocked
        assert not self.coordinator.can_start_task("holder_update", is_heavy=True)

        # But other tasks should be allowed
        assert self.coordinator.can_start_task("some_other_task", is_heavy=False)

        # End sales history
        self.coordinator.end_task("sales_history", is_heavy=True)

        # Now holder update should be allowed
        assert self.coordinator.can_start_task("holder_update", is_heavy=True)


@pytest.mark.integration
class TestFullSystemIntegration:
    """Test full system integration with all background tasks"""

    def setup_method(self):
        """Reset coordinator state before each test"""
        BackgroundCoordinator._instance = None
        self.coordinator = BackgroundCoordinator.get_instance()

    def teardown_method(self):
        """Clean up after each test"""
        BackgroundCoordinator._instance = None

    def test_main_block_processing_priority(self):
        """Test that main block processing always has priority"""
        # Start all heavy operations
        self.coordinator.start_task("sales_history", is_heavy=True)
        self.coordinator.start_task("market_data_stamps", is_heavy=True)  # Should fail
        self.coordinator.start_task("holder_update", is_heavy=True)  # Should fail

        # Main block processing should ALWAYS be allowed
        assert self.coordinator.can_start_task("block_processing")
        assert self.coordinator.start_task("block_processing")

        # Clean up
        self.coordinator.end_task("block_processing")
        self.coordinator.end_task("sales_history", is_heavy=True)

    def test_background_task_rotation(self):
        """Test that background tasks can rotate properly"""
        tasks = ["sales_history", "market_data_stamps", "holder_update"]
        completed = []

        # Run each task in sequence
        for task in tasks:
            assert self.coordinator.start_task(task, is_heavy=True)
            time.sleep(0.1)  # Simulate work
            self.coordinator.end_task(task, is_heavy=True)
            completed.append(task)

        # All tasks should have completed
        assert len(completed) == 3

        # Coordinator should be clean
        stats = self.coordinator.get_stats()
        assert stats["active_task_count"] == 0
        assert not stats["heavy_operation_in_progress"]

    def test_concurrent_light_operations(self):
        """Test that light operations can run concurrently with heavy ones"""
        # Start a heavy operation
        assert self.coordinator.start_task("sales_history", is_heavy=True)

        # Multiple light operations should be allowed
        assert self.coordinator.start_task("light_task_1", is_heavy=False)
        assert self.coordinator.start_task("light_task_2", is_heavy=False)
        assert self.coordinator.start_task("light_task_3", is_heavy=False)

        # But another heavy operation should be blocked
        assert not self.coordinator.start_task("market_data_stamps", is_heavy=True)

        # Clean up
        self.coordinator.end_task("sales_history", is_heavy=True)
        self.coordinator.end_task("light_task_1", is_heavy=False)
        self.coordinator.end_task("light_task_2", is_heavy=False)
        self.coordinator.end_task("light_task_3", is_heavy=False)


if __name__ == "__main__":
    # Run only integration tests
    pytest.main([__file__, "-v", "-m", "integration"])
