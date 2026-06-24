import asyncio
import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from index_core.background_validator import BackgroundValidator
from index_core.validation_queue import ValidationQueueManager


class TestValidationQueueManager:
    """Test the ValidationQueueManager functionality."""

    @pytest.fixture
    def queue_manager(self):
        """Create a ValidationQueueManager instance with temporary SQLite database."""
        # Clear singleton instance
        ValidationQueueManager._instance = None

        # Create temporary database file
        temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
        os.close(temp_fd)

        # Create instance with temporary DB
        manager = ValidationQueueManager(db_path=temp_path)

        yield manager

        # Cleanup
        ValidationQueueManager._instance = None
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def test_add_to_queue(self, queue_manager):
        """Test adding a block to the validation queue."""
        block_index = 906394
        ledger_hash = "test_hash_123"
        valid_src20_str = "test_src20_data"

        queue_manager.add_to_queue(block_index, ledger_hash, valid_src20_str)

        # Verify the data was added
        pending = queue_manager.get_pending_validations()
        assert len(pending) == 1
        assert pending[0][0] == block_index
        assert pending[0][1] == ledger_hash
        assert pending[0][2] == valid_src20_str

    def test_get_pending_validations(self, queue_manager):
        """Test retrieving pending validations."""
        # Add test data
        queue_manager.add_to_queue(906394, "hash1", "src20_data1")
        queue_manager.add_to_queue(906395, "hash2", "src20_data2")

        result = queue_manager.get_pending_validations(limit=10)

        assert len(result) == 2
        assert result[0] == (906394, "hash1", "src20_data1")
        assert result[1] == (906395, "hash2", "src20_data2")

    def test_mark_validated_success(self, queue_manager):
        """Test marking a block as successfully validated."""
        block_index = 906394
        api_hash = "api_hash_123"

        # Add test block
        queue_manager.add_to_queue(block_index, "local_hash", "src20_data")

        queue_manager.mark_validated(block_index, api_hash, is_valid=True)

        # Check stats to verify status change
        stats = queue_manager.get_validation_stats()
        assert "valid" in stats
        assert stats["valid"]["count"] == 1

    def test_mark_validated_mismatch(self, queue_manager):
        """Test marking a block with validation mismatch."""
        block_index = 906394
        api_hash = "different_hash"

        # Add test block
        queue_manager.add_to_queue(block_index, "local_hash", "src20_data")

        with patch("index_core.validation_queue.logger") as mock_logger:
            queue_manager.mark_validated(block_index, api_hash, is_valid=False)

            # Should log an error for mismatch
            mock_logger.error.assert_called_once()
            assert "Validation mismatch detected" in mock_logger.error.call_args[0][0]

        # Verify mismatch was recorded
        mismatches = queue_manager.get_mismatches()
        assert len(mismatches) == 1
        assert mismatches[0]["block_index"] == block_index

    def test_mark_api_error(self, queue_manager):
        """Test marking a validation attempt as failed."""
        block_index = 906394
        error_msg = "API timeout"

        # Add test block
        queue_manager.add_to_queue(block_index, "local_hash", "src20_data")

        queue_manager.mark_api_error(block_index, error_msg)

        # Verify retry count increased (would need to access DB directly to check)
        # For now, just verify it doesn't crash
        pending = queue_manager.get_pending_validations()
        assert len(pending) == 1  # Should still be pending

    def test_get_validation_stats(self, queue_manager):
        """Test getting validation statistics."""
        # Add various test data
        queue_manager.add_to_queue(906390, "hash1", "data1")
        queue_manager.add_to_queue(906391, "hash2", "data2")
        queue_manager.mark_validated(906390, "api_hash", True)

        result = queue_manager.get_validation_stats()

        assert "pending" in result
        assert "valid" in result
        assert result["pending"]["count"] == 1
        assert result["valid"]["count"] == 1

    def test_get_mismatches(self, queue_manager):
        """Test retrieving validation mismatches."""
        # Add test blocks and mark as mismatches
        queue_manager.add_to_queue(906394, "local_hash1", "data1")
        queue_manager.add_to_queue(906395, "local_hash2", "data2")
        queue_manager.mark_validated(906394, "api_hash1", False)
        queue_manager.mark_validated(906395, "api_hash2", False)

        result = queue_manager.get_mismatches()

        assert len(result) == 2
        assert result[0]["block_index"] == 906394
        assert result[0]["local_hash"] == "local_hash1"
        assert result[0]["api_hash"] == "api_hash1"

    def test_cleanup_old_entries(self, queue_manager):
        """Test cleanup of old validated entries."""
        # Add test block and mark as validated
        queue_manager.add_to_queue(906394, "hash", "data")
        queue_manager.mark_validated(906394, "api_hash", True)

        # Cleanup with 0 days retention (should delete immediately)
        deleted = queue_manager.cleanup_old_entries(days=0)

        assert deleted == 1

        # Verify it was deleted
        stats = queue_manager.get_validation_stats()
        assert stats.get("valid", {}).get("count", 0) == 0


class TestBackgroundValidator:
    """Test the BackgroundValidator functionality."""

    @pytest.fixture
    def validator(self):
        """Create a BackgroundValidator instance."""
        # Clear singleton
        ValidationQueueManager._instance = None

        # Create temp DB for testing
        temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
        os.close(temp_fd)

        # Create a mock queue manager
        mock_queue_manager = Mock(spec=ValidationQueueManager)

        # Patch the get_instance method before creating BackgroundValidator
        with patch.object(ValidationQueueManager, "get_instance", return_value=mock_queue_manager):
            validator = BackgroundValidator(check_interval=1)

        yield validator

        # Cleanup
        ValidationQueueManager._instance = None
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_start_stop(self, validator):
        """Test starting and stopping the validator."""
        assert not validator.is_running

        await validator.start()
        assert validator.is_running

        await validator.stop()
        assert not validator.is_running

    @pytest.mark.asyncio
    async def test_validation_loop_no_pending(self, validator):
        """Test validation loop when no pending validations."""
        validator.queue_manager.get_pending_validations = Mock(return_value=[])
        validator._should_run_validation = Mock(return_value=True)

        # Run one iteration
        validator.is_running = True
        task = asyncio.create_task(validator._validation_loop())
        await asyncio.sleep(0.1)
        validator.is_running = False
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        validator.queue_manager.get_pending_validations.assert_called()

    def test_should_run_validation(self, validator):
        """Validation is always permitted at the queue level under #782.

        Stampscan availability is now determined per-request via
        ``LedgerFetchStatus``; the legacy ``config.FORCE`` gate has been
        removed from ``_should_run_validation``.
        """
        assert validator._should_run_validation() is True

    @patch("index_core.background_validator.fetch_api_ledger_data")
    def test_process_validations_success(self, mock_fetch, validator):
        """Test processing validations successfully."""
        from index_core.src20 import LedgerFetchResult, LedgerFetchStatus

        pending = [(906394, "hash1", "src20_data1"), (906395, "hash2", "src20_data2")]

        # Mock API returns matching hashes (status OK = block_index matches)
        mock_fetch.side_effect = [
            LedgerFetchResult(LedgerFetchStatus.OK, "hash1", "balance_data_1"),
            LedgerFetchResult(LedgerFetchStatus.OK, "hash2", "balance_data_2"),
        ]

        validator._process_validations(pending)

        # Should mark both as validated
        assert validator.queue_manager.mark_validated.call_count == 2
        validator.queue_manager.mark_validated.assert_any_call(906394, "hash1", True)
        validator.queue_manager.mark_validated.assert_any_call(906395, "hash2", True)

    @patch("index_core.background_validator.fetch_api_ledger_data")
    def test_process_validations_mismatch(self, mock_fetch, validator):
        """Real consensus mismatch — status OK + hashes differ — must alert and mark invalid."""
        from index_core.src20 import LedgerFetchResult, LedgerFetchStatus

        pending = [(906394, "local_hash", "src20_data")]
        mock_fetch.return_value = LedgerFetchResult(LedgerFetchStatus.OK, "api_hash", "balance_data")

        with patch("index_core.background_validator.logger") as mock_logger:
            validator._process_validations(pending)

            # Should log error for mismatch
            mock_logger.error.assert_called()
            assert any("VALIDATION MISMATCH" in call.args[0] for call in mock_logger.error.call_args_list)

        validator.queue_manager.mark_validated.assert_called_with(906394, "api_hash", False)

    @patch("index_core.background_validator.fetch_api_ledger_data")
    def test_process_validations_api_error(self, mock_fetch, validator):
        """Non-OK status — block stays in queue, marked with the deferral reason."""
        from index_core.src20 import LedgerFetchResult, LedgerFetchStatus

        pending = [(906394, "hash1", "src20_data")]
        mock_fetch.return_value = LedgerFetchResult(LedgerFetchStatus.API_ERROR, None, None)

        validator._process_validations(pending)

        validator.queue_manager.mark_api_error.assert_called_once()
        call_args = validator.queue_manager.mark_api_error.call_args
        assert call_args.args[0] == 906394
        assert "deferred" in call_args.args[1]
        assert "api_error" in call_args.args[1]

    def test_get_status(self, validator):
        """Test getting validator status."""
        mock_stats = {"pending": {"count": 5}, "valid": {"count": 10}}
        validator.queue_manager.get_validation_stats = Mock(return_value=mock_stats)
        validator.is_running = True

        status = validator.get_status()

        assert status["is_running"] is True
        assert status["queue_stats"] == mock_stats
        assert status["check_interval"] == 1


class TestSrc20Integration:
    """Test integration with src20.py module."""

    @patch("index_core.validation_queue.ValidationQueueManager")
    @patch("index_core.src20.fetch_api_ledger_data")
    def test_validate_api_error_enqueues_and_continues(self, mock_fetch, mock_queue_class):
        """API_ERROR / NOT_INDEXED / BLOCK_INDEX_MISMATCH paths all enqueue
        the block for the background validator and return True so indexing
        continues. ``config.FORCE`` is no longer touched by this path."""
        from index_core.src20 import LedgerFetchResult, LedgerFetchStatus, validate_src20_ledger_hash

        mock_fetch.return_value = LedgerFetchResult(LedgerFetchStatus.API_ERROR, None, None)
        mock_queue_instance = Mock()
        mock_queue_instance.add_to_queue = Mock()
        mock_queue_class.get_instance.return_value = mock_queue_instance

        block_index = 906394
        ledger_hash = "test_hash"
        valid_src20_str = "test_data"

        assert validate_src20_ledger_hash(block_index, ledger_hash, valid_src20_str) is True

        mock_queue_class.get_instance.assert_called_once()
        mock_queue_instance.add_to_queue.assert_called_once_with(block_index, ledger_hash, valid_src20_str)

    @patch("index_core.validation_queue.ValidationQueueManager")
    @patch("index_core.src20.fetch_api_ledger_data")
    def test_validate_block_index_mismatch_enqueues(self, mock_fetch, mock_queue_class):
        """Stampscan shadow response (block_index < requested) also defers."""
        from index_core.src20 import LedgerFetchResult, LedgerFetchStatus, validate_src20_ledger_hash

        mock_fetch.return_value = LedgerFetchResult(LedgerFetchStatus.BLOCK_INDEX_MISMATCH, "shadow_hash", "shadow_data")
        mock_queue_instance = Mock()
        mock_queue_class.get_instance.return_value = mock_queue_instance

        assert validate_src20_ledger_hash(906394, "test_hash", "test_data") is True
        mock_queue_instance.add_to_queue.assert_called_once_with(906394, "test_hash", "test_data")

    @patch("index_core.src20.fetch_api_ledger_data")
    def test_validate_real_mismatch_returns_false(self, mock_fetch):
        """OK status + hashes differ = real consensus divergence → False.
        The caller (blocks.py) is expected to emit an ops_alerter notification."""
        from index_core.src20 import LedgerFetchResult, LedgerFetchStatus, validate_src20_ledger_hash

        mock_fetch.return_value = LedgerFetchResult(LedgerFetchStatus.OK, "stampscan_hash", "balance_data")
        assert validate_src20_ledger_hash(906394, "local_hash", "src20_data") is False

    @patch("index_core.src20.fetch_api_ledger_data")
    def test_validate_ok_matching_hashes(self, mock_fetch):
        """OK status + matching hashes = success path."""
        from index_core.src20 import LedgerFetchResult, LedgerFetchStatus, validate_src20_ledger_hash

        mock_fetch.return_value = LedgerFetchResult(LedgerFetchStatus.OK, "same_hash", "balance_data")
        assert validate_src20_ledger_hash(906394, "same_hash", "src20_data") is True

    @patch("index_core.src20.requests.get")
    def test_fetch_api_does_not_mutate_force(self, mock_get):
        """Even after max retries on API errors, fetch_api_ledger_data
        must NOT mutate ``config.FORCE``. Control flow is via the
        returned ``LedgerFetchStatus`` only."""
        import config as global_config
        from index_core.src20 import LedgerFetchStatus, fetch_api_ledger_data

        original_force = global_config.FORCE
        try:
            global_config.FORCE = False
            mock_get.side_effect = Exception("boom")
            result = fetch_api_ledger_data(123456)
            assert result.status == LedgerFetchStatus.API_ERROR
            assert global_config.FORCE is False
        finally:
            global_config.FORCE = original_force

    @patch("index_core.validation_queue.ValidationQueueManager")
    @patch("index_core.src20.fetch_api_ledger_data")
    def test_validate_not_indexed_enqueues(self, mock_fetch, mock_queue_class):
        """NOT_INDEXED status defers to background validator without raising."""
        from index_core.src20 import LedgerFetchResult, LedgerFetchStatus, validate_src20_ledger_hash

        mock_fetch.return_value = LedgerFetchResult(LedgerFetchStatus.NOT_INDEXED, None, None)
        mock_queue_instance = Mock()
        mock_queue_class.get_instance.return_value = mock_queue_instance

        assert validate_src20_ledger_hash(906394, "local_hash", "test_data") is True
        mock_queue_instance.add_to_queue.assert_called_once_with(906394, "local_hash", "test_data")

    @patch("index_core.src20.SRC_VALIDATION_API2", "https://test-api.com/{block_index}/{secret}")
    @patch("index_core.src20.SRC_VALIDATION_SECRET_API2", "test-secret")
    @patch("index_core.src20.time.sleep")
    @patch("index_core.src20.requests.get")
    def test_fetch_api_not_indexed_short_circuits_retries(self, mock_get, mock_sleep):
        """NOT_INDEXED is a definitive answer — must NOT retry. Guards against
        a future refactor reintroducing the legacy retry-on-any-failure loop."""
        from index_core.src20 import LedgerFetchStatus, fetch_api_ledger_data

        response = Mock()
        response.status_code = 200
        response.json.return_value = {"msg": "not_indexed"}
        mock_get.return_value = response

        result = fetch_api_ledger_data(800000)
        assert result.status == LedgerFetchStatus.NOT_INDEXED
        assert mock_get.call_count == 1
        assert mock_sleep.call_count == 0

    @patch("index_core.src20.SRC_VALIDATION_API2", "https://test-api.com/{block_index}/{secret}")
    @patch("index_core.src20.SRC_VALIDATION_SECRET_API2", "test-secret")
    @patch("index_core.src20.time.sleep")
    @patch("index_core.src20.requests.get")
    def test_fetch_api_block_index_mismatch_short_circuits_retries(self, mock_get, mock_sleep):
        """BLOCK_INDEX_MISMATCH (stampscan shadow) is also definitive."""
        from index_core.src20 import LedgerFetchStatus, fetch_api_ledger_data

        response = Mock()
        response.status_code = 200
        response.json.return_value = {"data": {"hash": "shadow_hash", "balance_data": "shadow_data", "block_index": "799995"}}
        mock_get.return_value = response

        result = fetch_api_ledger_data(800000)
        assert result.status == LedgerFetchStatus.BLOCK_INDEX_MISMATCH
        assert result.hash == "shadow_hash"
        assert mock_get.call_count == 1
        assert mock_sleep.call_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
