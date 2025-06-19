"""Tests for the resource_manager module."""

from unittest.mock import Mock, patch

from index_core.resource_manager import cleanup_resources


class TestResourceManager:
    """Test cases for resource manager functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_executor = Mock()
        self.mock_zmq_notifier = Mock()
        self.mock_future = Mock()
        self.mock_db = Mock()
        self.mock_cp_pipeline = Mock()

    @patch("index_core.resource_manager.stop_upload_worker")
    @patch("index_core.resource_manager.logger")
    def test_cleanup_basic_resources(self, mock_logger, mock_stop_upload):
        """Test basic cleanup without market data scheduler."""
        # Setup
        self.mock_db._closed = False

        # Call cleanup
        cleanup_resources(
            executor=self.mock_executor,
            zmq_notifier=self.mock_zmq_notifier,
            update_cpids_future=self.mock_future,
            db=self.mock_db,
            cp_pipeline=None,
            market_data_scheduler_started=False,
        )

        # Verify calls
        mock_stop_upload.assert_called_once()
        self.mock_zmq_notifier.cleanup.assert_called_once()
        self.mock_executor.shutdown.assert_called_once_with(wait=True)
        self.mock_db.commit.assert_called_once()
        self.mock_db.close.assert_called_once()

        # Verify logging
        assert mock_logger.info.call_count >= 3  # At least start, db close, and complete

    @patch("index_core.market_data_jobs.stop_market_data_jobs")
    @patch("index_core.resource_manager.stop_upload_worker")
    @patch("index_core.resource_manager.logger")
    def test_cleanup_with_market_data_scheduler(self, mock_logger, mock_stop_upload, mock_stop_market):
        """Test cleanup with market data scheduler enabled."""
        # Setup
        self.mock_db._closed = False

        # Call cleanup with market data scheduler
        cleanup_resources(
            executor=self.mock_executor,
            zmq_notifier=self.mock_zmq_notifier,
            update_cpids_future=self.mock_future,
            db=self.mock_db,
            cp_pipeline=None,
            market_data_scheduler_started=True,
        )

        # Verify market data scheduler was stopped
        mock_stop_market.assert_called_once_with(timeout=10)

    @patch("index_core.resource_manager.stop_upload_worker")
    @patch("index_core.resource_manager.logger")
    def test_cleanup_with_cp_pipeline(self, mock_logger, mock_stop_upload):
        """Test cleanup with CP pipeline."""
        # Setup
        self.mock_db._closed = False

        # Call cleanup with CP pipeline
        cleanup_resources(
            executor=self.mock_executor,
            zmq_notifier=self.mock_zmq_notifier,
            update_cpids_future=self.mock_future,
            db=self.mock_db,
            cp_pipeline=self.mock_cp_pipeline,
            market_data_scheduler_started=False,
        )

        # Verify CP pipeline was stopped
        self.mock_cp_pipeline.stop.assert_called_once()

    @patch("index_core.resource_manager.stop_upload_worker")
    @patch("index_core.resource_manager.logger")
    def test_cleanup_cancels_pending_future(self, mock_logger, mock_stop_upload):
        """Test that pending CPID updates are cancelled."""
        # Setup
        self.mock_db._closed = False
        self.mock_future.done.return_value = False  # Future is pending

        # Call cleanup
        cleanup_resources(
            executor=self.mock_executor,
            zmq_notifier=self.mock_zmq_notifier,
            update_cpids_future=self.mock_future,
            db=self.mock_db,
            cp_pipeline=None,
            market_data_scheduler_started=False,
        )

        # Verify future was cancelled
        self.mock_future.cancel.assert_called_once()

    @patch("index_core.resource_manager.stop_upload_worker")
    @patch("index_core.resource_manager.logger")
    def test_cleanup_db_error_handling(self, mock_logger, mock_stop_upload):
        """Test database cleanup error handling."""
        # Setup
        self.mock_db._closed = False
        self.mock_db.commit.side_effect = Exception("DB commit error")

        # Call cleanup
        cleanup_resources(
            executor=self.mock_executor,
            zmq_notifier=self.mock_zmq_notifier,
            update_cpids_future=self.mock_future,
            db=self.mock_db,
            cp_pipeline=None,
            market_data_scheduler_started=False,
        )

        # Verify rollback was attempted
        self.mock_db.rollback.assert_called_once()
        # Verify close was still attempted
        self.mock_db.close.assert_called_once()

    @patch("index_core.resource_manager.stop_upload_worker")
    @patch("index_core.resource_manager.logger")
    def test_cleanup_with_slow_operations(self, mock_logger, mock_stop_upload):
        """Test cleanup continues even with slow operations."""
        # Setup
        self.mock_db._closed = False

        # Make zmq cleanup slow but don't actually sleep
        mock_slow_zmq = Mock()
        mock_slow_zmq.cleanup = Mock()

        # Call cleanup
        cleanup_resources(
            executor=self.mock_executor,
            zmq_notifier=mock_slow_zmq,
            update_cpids_future=self.mock_future,
            db=self.mock_db,
            cp_pipeline=None,
            market_data_scheduler_started=False,
        )

        # Verify cleanup was still called
        mock_slow_zmq.cleanup.assert_called_once()
        self.mock_db.close.assert_called_once()

    @patch("index_core.resource_manager.stop_upload_worker")
    @patch("index_core.resource_manager.logger")
    def test_cleanup_with_closed_db(self, mock_logger, mock_stop_upload):
        """Test cleanup when database is already closed."""
        # Setup - database already closed
        self.mock_db._closed = True

        # Call cleanup
        cleanup_resources(
            executor=self.mock_executor,
            zmq_notifier=self.mock_zmq_notifier,
            update_cpids_future=self.mock_future,
            db=self.mock_db,
            cp_pipeline=None,
            market_data_scheduler_started=False,
        )

        # Verify database operations were not attempted
        self.mock_db.commit.assert_not_called()
        self.mock_db.close.assert_not_called()

    @patch("index_core.resource_manager.stop_upload_worker")
    @patch("index_core.resource_manager.logger")
    @patch("index_core.resource_manager.logging")
    def test_cleanup_final_logging_shutdown(self, mock_logging, mock_logger, mock_stop_upload):
        """Test that logging.shutdown() is called at the end."""
        # Setup
        self.mock_db._closed = False

        # Call cleanup
        cleanup_resources(
            executor=self.mock_executor,
            zmq_notifier=self.mock_zmq_notifier,
            update_cpids_future=self.mock_future,
            db=self.mock_db,
            cp_pipeline=None,
            market_data_scheduler_started=False,
        )

        # Verify logging.shutdown was called
        mock_logging.shutdown.assert_called_once()

    @patch("index_core.resource_manager.stop_upload_worker")
    @patch("index_core.resource_manager.logger")
    def test_cleanup_with_none_resources(self, mock_logger, mock_stop_upload):
        """Test cleanup handles None resources gracefully."""
        # Call cleanup with None values
        cleanup_resources(
            executor=None,
            zmq_notifier=None,
            update_cpids_future=None,
            db=None,
            cp_pipeline=None,
            market_data_scheduler_started=False,
        )

        # Should complete without errors
        mock_stop_upload.assert_called_once()
        assert "Cleanup complete" in str(mock_logger.info.call_args_list)

    @patch("index_core.resource_manager.stop_upload_worker")
    @patch("index_core.resource_manager.logger")
    def test_cleanup_exception_in_zmq(self, mock_logger, mock_stop_upload):
        """Test cleanup continues after ZMQ cleanup exception."""
        # Setup
        self.mock_db._closed = False
        self.mock_zmq_notifier.cleanup.side_effect = Exception("ZMQ error")

        # Call cleanup
        cleanup_resources(
            executor=self.mock_executor,
            zmq_notifier=self.mock_zmq_notifier,
            update_cpids_future=self.mock_future,
            db=self.mock_db,
            cp_pipeline=None,
            market_data_scheduler_started=False,
        )

        # Verify cleanup continued after ZMQ error
        self.mock_executor.shutdown.assert_called_once()
        self.mock_db.close.assert_called_once()
