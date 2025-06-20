"""Comprehensive tests for pipeline_utils.py module."""

import concurrent.futures
import logging
import threading
import time
from unittest import mock

import pytest

from index_core.pipeline_utils import CPBlocksPipeline


@pytest.fixture(autouse=True)
def mock_config_values():
    """Mock config values for tests."""
    with mock.patch("index_core.pipeline_utils.config") as mock_cfg:
        mock_cfg.CP_STAMP_GENESIS_BLOCK = 820000
        mock_cfg.TESTNET = False
        mock_cfg.DEFAULT_BACKEND_PORT = 8332
        yield mock_cfg


@pytest.fixture
def mock_backend_instance():
    """Mock Backend instance."""
    mock_instance = mock.MagicMock()
    mock_instance.getblockcount.return_value = 820100
    mock_instance.invalidate_blockcount_cache.return_value = None

    with mock.patch("index_core.pipeline_utils.Backend") as mock_backend_cls:
        mock_backend_cls.return_value = mock_instance
        with mock.patch("index_core.pipeline_utils.backend_instance", mock_instance):
            yield mock_instance


@pytest.fixture
def mock_pipeline_logger():
    """Mock logger for pipeline_utils."""
    with mock.patch("index_core.pipeline_utils.logger") as mock_log:
        yield mock_log


@pytest.fixture
def mock_fsm():
    """Mock fallback state manager."""
    with mock.patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_get_fsm:
        mock_mgr = mock.MagicMock()
        mock_mgr.is_fallback_active.return_value = False
        mock_mgr.get_failed_blocks.return_value = set()
        mock_mgr.get_fallback_start_block.return_value = None
        mock_get_fsm.return_value = mock_mgr
        yield mock_mgr


@pytest.fixture
def mock_health():
    """Mock node health functions."""
    with mock.patch("index_core.pipeline_utils.get_healthy_nodes") as mock_get, mock.patch(
        "index_core.pipeline_utils.update_healthy_nodes"
    ) as mock_update, mock.patch("index_core.pipeline_utils.is_shutdown_requested") as mock_shutdown:
        mock_get.return_value = [{"name": "test_node", "url": "http://test:8080"}]
        mock_shutdown.return_value = False
        yield {"get": mock_get, "update": mock_update, "shutdown": mock_shutdown}


@pytest.fixture
def mock_fetch_blocks():
    """Mock fetch_xcp_blocks_concurrent function."""
    with mock.patch("index_core.pipeline_utils.fetch_xcp_blocks_concurrent") as mock_fetch:

        def side_effect(start, end):
            result = {}
            for i in range(start, min(end + 1, start + 150)):
                result[i] = {"block_index": i, "xcp_block_hash": f"hash_{i}", "issuances": [], "transactions": []}
            return result

        mock_fetch.side_effect = side_effect
        yield mock_fetch


class TestCPBlocksPipeline:
    """Test CPBlocksPipeline class."""

    def test_init(self, mock_fsm):
        pipeline = CPBlocksPipeline()
        assert pipeline.max_queue_size == 600
        assert pipeline.fallback_mode is True

    def test_start(self, mock_backend_instance, mock_health, mock_fsm, mock_pipeline_logger):
        pipeline = CPBlocksPipeline()
        with mock.patch.object(pipeline, "_fetch_blocks_worker"), mock.patch.object(
            pipeline, "wait_for_initial_blocks", return_value=True
        ), mock.patch("threading.Thread") as mock_thread_cls:
            mock_thread = mock.MagicMock()
            mock_thread.is_alive.return_value = True
            mock_thread_cls.return_value = mock_thread
            pipeline.start(820010)
            assert pipeline.current_block == 820010
            assert pipeline.running is True
            mock_thread.start.assert_called_once()

    def test_get_block_success(self):
        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820010
        test_block = {"block_index": 820010, "transactions": [], "issuances": []}
        with pipeline._lock:
            pipeline.queue[820010] = test_block
        result = pipeline.get_block(820010)
        assert result == test_block
        assert pipeline.current_block == 820011
        assert 820010 not in pipeline.queue

    def test_get_block_out_of_sequence_behind(self, mock_pipeline_logger):
        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820020
        test_block = {"block_index": 820010, "transactions": [], "issuances": []}
        with pipeline._lock:
            pipeline.queue[820010] = test_block
        result = pipeline.get_block(820010)
        assert result == test_block
        assert pipeline.current_block == 820020  # State should not advance
        assert 820010 not in pipeline.queue
        mock_pipeline_logger.debug.assert_called()

    def test_get_block_out_of_sequence_ahead(self, mock_pipeline_logger):
        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820010
        test_block = {"block_index": 820020, "transactions": [], "issuances": []}
        with pipeline._lock:
            pipeline.queue[820020] = test_block
        result = pipeline.get_block(820020)
        assert result == test_block
        assert pipeline.current_block == 820010  # State should not advance
        assert 820020 in pipeline.queue  # Should not be popped
        mock_pipeline_logger.debug.assert_called()

    def test_get_block_not_in_queue(self):
        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820010
        result = pipeline.get_block(820010)
        assert result is None

    def test_worker_fetches_and_populates_queue(self, mock_backend_instance, mock_health, mock_fetch_blocks):
        pipeline = CPBlocksPipeline(target_queue_size=10)
        pipeline.start(820000)

        # Let the worker run and then stop it, which now waits for tasks to complete
        time.sleep(0.2)  # A short sleep to ensure the worker starts
        pipeline.stop()

        # Check queue has items and the first block is present
        assert len(pipeline.queue) > 0
        assert 820000 in pipeline.queue
        assert "transactions" in pipeline.queue[820000]

    def test_worker_respects_shutdown_flag(self, mock_backend_instance, mock_health, mock_fetch_blocks):
        pipeline = CPBlocksPipeline()
        pipeline.start(820000)
        # Immediately stop
        pipeline.stop()
        # Worker thread should join successfully
        pipeline.worker_thread.join(timeout=1)
        assert not pipeline.worker_thread.is_alive()

    def test_process_completed_futures_handles_results(self, mock_fetch_blocks):
        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820000
        future = concurrent.futures.Future()
        future.set_result(
            {
                820000: {"block_index": 820000, "issuances": []},
                820001: {"block_index": 820001, "issuances": []},
            }
        )
        fetch_futures = {820000: future, 820001: future}
        pipeline._process_completed_futures(fetch_futures)
        with pipeline._lock:
            assert 820000 in pipeline.queue
            assert 820001 in pipeline.queue
        assert not fetch_futures  # Should be empty after processing

    def test_process_completed_futures_discards_old_blocks(self, mock_pipeline_logger):
        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820010  # Processor has moved on
        future = concurrent.futures.Future()
        future.set_result({820005: {"block_index": 820005, "issuances": []}})
        fetch_futures = {820005: future}
        pipeline._process_completed_futures(fetch_futures)
        assert 820005 not in pipeline.queue
        mock_pipeline_logger.warning.assert_called_with(
            "Discarding already processed block 820005 from completed future (processor is at 820010)."
        )

    def test_fetch_batch_success(self, mock_fetch_blocks):
        pipeline = CPBlocksPipeline()
        # The _fetch_blocks_batch is an internal method, we test it directly
        result = pipeline._fetch_blocks_batch(list(range(820000, 820005)), "http://test-node")
        assert len(result) == 5
        assert 820000 in result
        # Verify that the mocked function was called correctly
        mock_fetch_blocks.assert_called_once_with(820000, 820004)

    def test_fetch_batch_failure(self, mock_fetch_blocks):
        mock_fetch_blocks.side_effect = Exception("Total fetch failure")
        pipeline = CPBlocksPipeline()
        result = pipeline._fetch_blocks_batch(list(range(820000, 820005)), "http://test-node")
        assert result == {}

    def test_fallback_mode_enters_and_persists_state(self, mock_backend_instance, mock_health, mock_fsm, mock_pipeline_logger):
        # Simulate no healthy nodes
        mock_health["get"].return_value = []

        pipeline = CPBlocksPipeline()
        pipeline.start(820000)

        # Allow worker to run and detect node failure
        time.sleep(1)

        # Stop the pipeline to ensure state is flushed if needed
        pipeline.stop()

        # Assert that fallback mode was entered and state was persisted
        assert pipeline.fallback_started_at == 820000
        mock_fsm.start_fallback_mode.assert_called_once_with(820000)

    def test_concurrent_access(self, mock_backend_instance, mock_health, mock_fetch_blocks):
        pipeline = CPBlocksPipeline()
        pipeline.start(820000)
        errors = []

        def consumer_thread():
            try:
                for i in range(820000, 820050):
                    block = None
                    # Aggressively try to get the next block
                    while not block:
                        block = pipeline.get_block(i)
                        if not block:
                            time.sleep(0.001)  # Small sleep to yield
            except Exception as e:
                logging.error(f"Consumer error: {e}")
                errors.append(e)

        consumer = threading.Thread(target=consumer_thread)
        consumer.start()

        # Let the pipeline run for a bit
        time.sleep(1)

        # Stop the pipeline
        pipeline.stop()
        consumer.join(timeout=2)

        assert not errors
        assert pipeline.current_block > 820000
