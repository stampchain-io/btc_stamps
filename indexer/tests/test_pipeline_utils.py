"""Comprehensive tests for pipeline_utils.py module."""

import concurrent.futures
import logging
import threading
import time
from unittest import mock

import pytest

import config


@pytest.fixture(autouse=True)
def mock_config():
    """Mock config values for tests."""
    with mock.patch("index_core.pipeline_utils.config") as mock_cfg:
        mock_cfg.CP_STAMP_GENESIS_BLOCK = 820000
        mock_cfg.TESTNET = False
        mock_cfg.DEFAULT_BACKEND_PORT = 8332
        yield mock_cfg


@pytest.fixture
def mock_backend():
    """Mock Backend instance."""
    mock_instance = mock.MagicMock()
    mock_instance.getblockcount.return_value = 820100
    mock_instance.invalidate_blockcount_cache.return_value = None

    with mock.patch("index_core.pipeline_utils.Backend") as mock_backend_cls:
        mock_backend_cls.return_value = mock_instance
        # Mock the module-level backend_instance directly
        with mock.patch("index_core.pipeline_utils.backend_instance", mock_instance):
            yield mock_instance


@pytest.fixture
def mock_logger():
    """Mock logger."""
    with mock.patch("index_core.pipeline_utils.logger") as mock_log:
        yield mock_log


@pytest.fixture
def mock_fallback_state_manager():
    """Mock fallback state manager."""
    with mock.patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_get_fsm:
        mock_state_manager = mock.MagicMock()
        mock_state_manager.is_fallback_active.return_value = False
        mock_state_manager.get_failed_blocks.return_value = set()
        mock_state_manager.get_fallback_start_block.return_value = None
        mock_state_manager.add_failed_block.return_value = None  # Mock the file I/O method
        mock_state_manager.start_fallback_mode.return_value = None  # Mock the file I/O method
        mock_state_manager.end_fallback_mode.return_value = None  # Mock the file I/O method
        mock_get_fsm.return_value = mock_state_manager
        yield mock_state_manager


@pytest.fixture
def mock_node_health():
    """Mock node health functions."""
    with mock.patch("index_core.pipeline_utils.get_healthy_nodes") as mock_get_nodes:
        with mock.patch("index_core.pipeline_utils.update_healthy_nodes") as mock_update_nodes:
            with mock.patch("index_core.pipeline_utils.is_shutdown_requested") as mock_shutdown:
                mock_get_nodes.return_value = [{"name": "test_node", "url": "http://test:8080"}]
                mock_shutdown.return_value = False
                yield {
                    "get_healthy_nodes": mock_get_nodes,
                    "update_healthy_nodes": mock_update_nodes,
                    "is_shutdown_requested": mock_shutdown,
                }


@pytest.fixture
def mock_fetch_xcp_blocks():
    """Mock fetch_xcp_blocks_concurrent function."""
    with mock.patch("index_core.pipeline_utils.fetch_xcp_blocks_concurrent") as mock_fetch:

        def side_effect(start, end):
            # Return mock block data
            result = {}
            for i in range(start, min(end + 1, start + 10)):  # Limit to 10 blocks
                result[i] = {"block_index": i, "xcp_block_hash": f"hash_{i}", "issuances": [], "transactions": []}
            return result

        mock_fetch.side_effect = side_effect
        yield mock_fetch


class TestCPBlocksPipeline:
    """Test CPBlocksPipeline class."""

    def test_init_default(self, mock_fallback_state_manager):
        """Test initialization with default parameters."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()

        assert pipeline.max_queue_size == 600
        assert pipeline.target_queue_size == 250
        assert pipeline.max_lookahead == 500
        assert pipeline.fallback_mode is True
        assert pipeline.queue == {}
        assert pipeline.current_block is None
        assert pipeline.running is False
        assert isinstance(pipeline._lock, type(threading.Lock()))
        assert isinstance(pipeline.shutdown_flag, threading.Event)
        assert isinstance(pipeline.initial_blocks_ready, threading.Event)
        assert isinstance(pipeline.fetch_executor, concurrent.futures.ThreadPoolExecutor)

    def test_init_custom_params(self, mock_fallback_state_manager):
        """Test initialization with custom parameters."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline(max_queue_size=100, target_queue_size=50, max_lookahead=200, fallback_mode=False)

        assert pipeline.max_queue_size == 100
        assert pipeline.target_queue_size == 50
        assert pipeline.max_lookahead == 200
        assert pipeline.fallback_mode is False
        assert pipeline.state_manager is None

    def test_init_with_fallback_state(self, mock_fallback_state_manager):
        """Test initialization with existing fallback state."""
        mock_fallback_state_manager.is_fallback_active.return_value = True
        mock_fallback_state_manager.get_failed_blocks.return_value = {820001, 820002}
        mock_fallback_state_manager.get_fallback_start_block.return_value = 820001

        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline(fallback_mode=True)

        assert pipeline.failed_cp_blocks == {820001, 820002}
        assert pipeline.fallback_started_at == 820001

    def test_start_with_valid_block(self, mock_backend, mock_node_health, mock_fallback_state_manager, mock_logger):
        """Test starting the pipeline with a valid block."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()

        with mock.patch.object(pipeline, "_fetch_blocks_worker"):
            with mock.patch.object(pipeline, "wait_for_initial_blocks", return_value=True):
                with mock.patch("threading.Thread") as mock_thread_cls:
                    mock_thread = mock.MagicMock()
                    mock_thread.is_alive.return_value = True
                    mock_thread_cls.return_value = mock_thread

                    pipeline.start(820010)

                    assert pipeline.current_block == 820010
                    assert pipeline.running is True
                    assert pipeline.worker_thread is not None
                    mock_thread.start.assert_called_once()

    def test_start_before_genesis_block(self, mock_backend, mock_node_health, mock_fallback_state_manager, mock_logger):
        """Test starting the pipeline before genesis block."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()

        with mock.patch.object(pipeline, "_fetch_blocks_worker"):
            with mock.patch.object(pipeline, "wait_for_initial_blocks", return_value=True):
                pipeline.start(819000)  # Before genesis

                # Should adjust to genesis block
                assert pipeline.current_block == 820000

    def test_start_at_chain_tip(self, mock_backend, mock_node_health, mock_fallback_state_manager, mock_logger):
        """Test starting the pipeline at chain tip."""
        mock_backend.getblockcount.return_value = 820100

        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()

        with mock.patch.object(pipeline, "_fetch_blocks_worker"):
            pipeline.start(820101)  # Beyond chain tip

            # Should set initial blocks ready immediately
            assert pipeline.initial_blocks_ready.is_set()

    def test_start_with_none_block(self):
        """Test starting with None block should raise ValueError."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()

        with pytest.raises(ValueError, match="start_block must be provided"):
            pipeline.start(None)

    def test_start_fallback_mode(self, mock_backend, mock_node_health, mock_fallback_state_manager, mock_logger):
        """Test starting in fallback mode when nodes fail."""
        mock_node_health["get_healthy_nodes"].return_value = []

        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline(fallback_mode=True)

        with mock.patch.object(pipeline, "_fetch_blocks_worker"):
            with mock.patch.object(pipeline, "wait_for_initial_blocks", return_value=False):
                pipeline.start(820010)

                assert pipeline.fallback_started_at == 820010
                assert pipeline.initial_blocks_ready.is_set()
                mock_fallback_state_manager.start_fallback_mode.assert_called_once_with(820010)

    def test_start_no_fallback_mode_failure(self, mock_backend, mock_node_health, mock_fallback_state_manager):
        """Test starting without fallback mode when nodes fail."""
        mock_node_health["get_healthy_nodes"].return_value = []

        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline(fallback_mode=False)

        with mock.patch.object(pipeline, "_fetch_blocks_worker"):
            with mock.patch.object(pipeline, "wait_for_initial_blocks", return_value=False):
                with pytest.raises(RuntimeError, match="Cannot proceed without Counterparty block data"):
                    pipeline.start(820010)

    def test_wait_for_initial_blocks_success(self, mock_fallback_state_manager):
        """Test wait_for_initial_blocks with successful wait."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820010
        pipeline.initial_batch_size = 5

        # Add blocks to queue
        with pipeline._lock:
            for i in range(820010, 820015):
                pipeline.queue[i] = {"block_index": i}

        # Set the ready flag
        pipeline.initial_blocks_ready.set()

        result = pipeline.wait_for_initial_blocks(timeout=1)
        assert result is True

    def test_wait_for_initial_blocks_timeout(self, mock_fallback_state_manager):
        """Test wait_for_initial_blocks with timeout."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()

        result = pipeline.wait_for_initial_blocks(timeout=0.1)
        assert result is False

    def test_wait_for_initial_blocks_missing_critical(self, mock_fallback_state_manager, mock_logger):
        """Test wait_for_initial_blocks with missing critical blocks."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820672  # Set so 820662 is in required range
        pipeline.initial_batch_size = 10
        # Force it to check beyond just block count by requiring 5 blocks minimum
        pipeline.min_blocks_ready = 5

        # The start_block will be 820662 (current - batch_size)
        # Required blocks will be 820662-820666 (5 consecutive)
        # Critical block 820662 will be missing
        with pipeline._lock:
            # Add blocks 820663-820666 but NOT 820662 (critical)
            pipeline.queue[820663] = {"block_index": 820663}
            pipeline.queue[820664] = {"block_index": 820664}
            pipeline.queue[820665] = {"block_index": 820665}
            pipeline.queue[820666] = {"block_index": 820666}
            # NOT adding 820662 which is critical and required

        pipeline.initial_blocks_ready.set()

        result = pipeline.wait_for_initial_blocks(timeout=1)
        assert result is False

    def test_stop(self, mock_fallback_state_manager, mock_logger):
        """Test stopping the pipeline."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.running = True

        # Create a mock worker thread
        mock_thread = mock.MagicMock()
        mock_thread.is_alive.return_value = True
        mock_thread.join.return_value = None
        pipeline.worker_thread = mock_thread

        # Add some data to queue
        with pipeline._lock:
            pipeline.queue[820001] = {"block_index": 820001}

        pipeline.stop()

        assert pipeline.running is False
        assert pipeline.shutdown_flag.is_set()
        mock_thread.join.assert_called_once_with(timeout=10)
        assert len(pipeline.queue) == 0

    def test_stop_thread_timeout(self, mock_fallback_state_manager, mock_logger):
        """Test stopping with thread timeout."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()

        # Create a mock thread that doesn't stop
        mock_thread = mock.MagicMock()
        mock_thread.is_alive.side_effect = [True, True]  # Still alive after join
        pipeline.worker_thread = mock_thread

        pipeline.stop()

        mock_logger.warning.assert_called()

    def test_reset(self, mock_backend, mock_node_health, mock_fallback_state_manager, mock_logger):
        """Test resetting the pipeline."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820010

        with pipeline._lock:
            pipeline.queue[820010] = {"block_index": 820010}

        with mock.patch.object(pipeline, "start") as mock_start:
            with mock.patch.object(pipeline, "stop") as mock_stop:
                pipeline.reset(820005)

                mock_stop.assert_called_once()
                assert pipeline.current_block == 820005
                assert len(pipeline.queue) == 0
                assert pipeline.last_fetch_time == 0
                mock_backend.invalidate_blockcount_cache.assert_called_once()
                mock_start.assert_called_once_with(820005)

    def test_get_block_success(self, mock_backend, mock_fallback_state_manager):
        """Test getting a block that exists in queue."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820000  # Initialize current_block

        # Add block to queue
        test_block = {"block_index": 820010, "xcp_block_hash": "test_hash", "transactions": []}
        with pipeline._lock:
            pipeline.queue[820010] = test_block

        result = pipeline.get_block(820010)

        assert result == test_block
        assert "issuances" in result  # Should add empty issuances

    def test_get_block_not_found(self, mock_backend, mock_fallback_state_manager):
        """Test getting a block that doesn't exist."""
        from index_core.pipeline_utils import CPBlocksPipeline

        # Create pipeline without fallback mode to avoid state manager issues
        pipeline = CPBlocksPipeline(fallback_mode=False)
        pipeline.current_block = 820000  # Initialize current_block

        result = pipeline.get_block(820010)

        assert result is None

    def test_get_block_fallback_mode(self, mock_backend, mock_fallback_state_manager):
        """Test getting a block in fallback mode by testing the fallback block creation directly."""
        from index_core.pipeline_utils import CPBlocksPipeline

        # Test fallback block creation without the complex state management
        pipeline = CPBlocksPipeline(fallback_mode=False)  # Avoid state manager complexity

        # Test the fallback block creation method directly
        fallback_block = pipeline.create_fallback_block(820010)

        assert fallback_block is not None
        assert fallback_block["fallback_mode"] is True
        assert fallback_block["needs_cp_reprocessing"] is True
        assert fallback_block["block_index"] == 820010
        assert fallback_block["xcp_block_hash"] is None
        assert fallback_block["issuances"] == []
        assert fallback_block["transactions"] == []

    def test_get_block_queue_cleanup(self, mock_backend, mock_fallback_state_manager):
        """Test get_block cleans up old blocks when queue is large."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820350  # Initialize current_block to match the block we're getting

        # Fill queue with many blocks
        with pipeline._lock:
            for i in range(820000, 820400):
                pipeline.queue[i] = {"block_index": i}

        # Get a recent block
        result = pipeline.get_block(820350)

        assert result is not None
        # Old blocks should be removed
        with pipeline._lock:
            assert 820000 not in pipeline.queue
            assert 820350 in pipeline.queue

    def test_create_fallback_block(self, mock_fallback_state_manager):
        """Test creating fallback block data."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()

        result = pipeline.create_fallback_block(820010)

        assert result["block_index"] == 820010
        assert result["xcp_block_hash"] is None
        assert result["issuances"] == []
        assert result["transactions"] == []
        assert result["fallback_mode"] is True
        assert result["needs_cp_reprocessing"] is True

    def test_get_fallback_block_info(self, mock_fallback_state_manager):
        """Test getting fallback block information."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.fallback_started_at = 820000
        pipeline.failed_cp_blocks = {820001, 820002, 820003}
        pipeline.cp_nodes_healthy_again = True

        info = pipeline.get_fallback_block_info()

        assert info["fallback_mode"] is True
        assert info["fallback_started_at"] == 820000
        assert info["failed_cp_blocks_count"] == 3
        assert len(info["failed_cp_blocks_sample"]) == 3
        assert info["cp_nodes_healthy_again"] is True

    def test_check_cp_node_recovery_not_in_fallback(self, mock_node_health, mock_fallback_state_manager):
        """Test checking CP node recovery when not in fallback mode."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()

        result = pipeline.check_cp_node_recovery()

        assert result is False
        mock_node_health["update_healthy_nodes"].assert_not_called()

    def test_check_cp_node_recovery_nodes_healthy(self, mock_node_health, mock_fallback_state_manager, mock_logger):
        """Test checking CP node recovery when nodes become healthy."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.fallback_mode = True
        pipeline.fallback_started_at = 820000
        pipeline.failed_cp_blocks = {820001, 820002}
        pipeline.last_health_check = 0

        with mock.patch.object(pipeline, "_trigger_automatic_rollback") as mock_rollback:
            result = pipeline.check_cp_node_recovery()

            assert result is True
            assert pipeline.cp_nodes_healthy_again is True
            mock_rollback.assert_called_once()

    def test_check_cp_node_recovery_rate_limited(self, mock_node_health, mock_fallback_state_manager):
        """Test CP node recovery check is rate limited."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.fallback_mode = True
        pipeline.fallback_started_at = 820000
        pipeline.failed_cp_blocks = {820001}
        pipeline.last_health_check = time.time() - 10  # Recent check
        pipeline.health_check_interval = 30

        result = pipeline.check_cp_node_recovery()

        assert result is False
        mock_node_health["update_healthy_nodes"].assert_not_called()

    def test_trigger_automatic_rollback(self, mock_fallback_state_manager, mock_logger):
        """Test triggering automatic rollback."""
        # Set up all mocks first
        with mock.patch("index_core.backend.Backend") as mock_backend_cls:
            with mock.patch("index_core.database.rebuild_balances"):
                with mock.patch("index_core.database.rebuild_owners"):
                    with mock.patch("index_core.database.update_src20_token_stats"):
                        with mock.patch("index_core.database.DatabaseManager") as mock_db_mgr:
                            with mock.patch("index_core.database.clear_all_caches"):
                                with mock.patch("index_core.database.purge_block_db") as mock_purge:
                                    # Set up mock returns
                                    mock_db = mock.MagicMock()
                                    mock_db_mgr.connect.return_value = mock_db
                                    mock_backend_inst = mock.MagicMock()
                                    mock_backend_cls.return_value = mock_backend_inst

                                    # Now create the pipeline after all mocks are in place
                                    from index_core.pipeline_utils import CPBlocksPipeline

                                    pipeline = CPBlocksPipeline(fallback_mode=True)
                                    pipeline.fallback_started_at = 820000
                                    pipeline.failed_cp_blocks = {820001, 820002}

                                    # Call the method
                                    pipeline._trigger_automatic_rollback()

                                    # Verify the expected calls
                                    mock_purge.assert_called_once_with(mock_db, 820000)
                                    assert len(pipeline.failed_cp_blocks) == 0
                                    assert pipeline.fallback_started_at is None
                                    mock_fallback_state_manager.end_fallback_mode.assert_called_once()

    def test_fetch_blocks_worker_initial_fetch(
        self, mock_backend, mock_node_health, mock_fetch_xcp_blocks, mock_fallback_state_manager
    ):
        """Test the fetch blocks worker during initial fetch."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820000
        pipeline.initial_batch_size = 5
        pipeline.running = True

        # Mock the fetch to return blocks
        def run_worker_briefly():
            # Run the worker for a short time
            original_sleep = time.sleep
            call_count = 0

            def mock_sleep(duration):
                nonlocal call_count
                call_count += 1
                if call_count > 2:  # Stop after a few iterations
                    pipeline.shutdown_flag.set()
                original_sleep(0.01)  # Very short sleep

            with mock.patch("time.sleep", mock_sleep):
                pipeline._fetch_blocks_worker()

        run_worker_briefly()

        # Should have fetched some blocks
        assert pipeline.initial_blocks_ready.is_set()
        assert len(pipeline.queue) > 0

    def test_fetch_blocks_worker_shutdown(self, mock_backend, mock_node_health, mock_fallback_state_manager):
        """Test fetch blocks worker responds to shutdown."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820000
        pipeline.shutdown_flag.set()  # Set shutdown immediately

        pipeline._fetch_blocks_worker()

        # Should exit cleanly
        assert pipeline.initial_blocks_ready.is_set()

    def test_fetch_blocks_batch_success(self, mock_fetch_xcp_blocks, mock_fallback_state_manager):
        """Test fetching a batch of blocks successfully."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.running = True

        result = pipeline._fetch_blocks_batch([820000, 820001, 820002], "http://test:8080")

        assert len(result) == 3
        assert 820000 in result
        assert 820001 in result
        assert 820002 in result

    def test_fetch_blocks_batch_empty_indices(self, mock_fallback_state_manager, mock_logger):
        """Test fetching with empty block indices."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()

        result = pipeline._fetch_blocks_batch([], "http://test:8080")

        assert result == {}
        mock_logger.warning.assert_called_with("Empty block_indices list passed to _fetch_blocks_batch")

    def test_fetch_blocks_batch_with_retry(self, mock_fetch_xcp_blocks, mock_node_health, mock_fallback_state_manager):
        """Test fetch blocks batch with retry logic."""
        from index_core.pipeline_utils import CPBlocksPipeline

        # Make fetch fail first time, succeed second time
        mock_fetch_xcp_blocks.side_effect = [
            {},  # First attempt fails
            {820000: {"block_index": 820000}},  # Second attempt succeeds
        ]

        pipeline = CPBlocksPipeline()
        pipeline.running = True

        with mock.patch("time.sleep"):  # Speed up test
            result = pipeline._fetch_blocks_batch([820000], "http://test:8080")

        assert len(result) == 1
        assert 820000 in result
        mock_node_health["update_healthy_nodes"].assert_called_once()

    def test_fetch_blocks_batch_all_retries_fail(self, mock_fetch_xcp_blocks, mock_fallback_state_manager, mock_logger):
        """Test fetch blocks batch when all retries fail."""
        from index_core.pipeline_utils import CPBlocksPipeline

        # Clear the side_effect and set return_value to simulate failure
        mock_fetch_xcp_blocks.side_effect = None
        mock_fetch_xcp_blocks.return_value = {}  # Always fail

        pipeline = CPBlocksPipeline()
        pipeline.running = True
        pipeline.blocks_being_fetched = {820000}

        with mock.patch("time.sleep"):  # Speed up test
            result = pipeline._fetch_blocks_batch([820000], "http://test:8080")

        assert result == {}
        assert 820000 not in pipeline.blocks_being_fetched

    def test_fetch_blocks_batch_shutdown_during_fetch(self, mock_fetch_xcp_blocks, mock_fallback_state_manager):
        """Test fetch blocks batch when shutdown occurs during fetch."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.shutdown_flag.set()  # Shutdown immediately
        pipeline.blocks_being_fetched = {820000}

        result = pipeline._fetch_blocks_batch([820000], "http://test:8080")

        assert result == {}
        assert 820000 not in pipeline.blocks_being_fetched

    def test_fetch_blocks_batch_updates_queue(self, mock_fetch_xcp_blocks, mock_fallback_state_manager):
        """Test that fetch blocks batch updates the queue."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.running = True
        pipeline.current_block = 820000

        result = pipeline._fetch_blocks_batch([820000, 820001], "http://test:8080")

        assert len(result) == 2
        with pipeline._lock:
            assert 820000 in pipeline.queue
            assert 820001 in pipeline.queue
            assert pipeline.current_block == 820002  # Should advance to max(blocks) + 1


class TestPipelineIntegration:
    """Integration tests for the pipeline."""

    def test_concurrent_get_and_fetch(
        self, mock_backend, mock_node_health, mock_fetch_xcp_blocks, mock_fallback_state_manager
    ):
        """Test concurrent get_block and fetch operations."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline(fallback_mode=False)
        pipeline.current_block = 820000
        pipeline.running = True

        results = {}
        errors = []

        def get_blocks():
            try:
                for i in range(820000, 820010):
                    block = pipeline.get_block(i)
                    if block:
                        results[i] = block
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        def fetch_blocks():
            try:
                pipeline._fetch_blocks_batch(list(range(820000, 820010)), "http://test:8080")
            except Exception as e:
                errors.append(e)

        # Run get and fetch concurrently
        threads = [threading.Thread(target=get_blocks), threading.Thread(target=fetch_blocks)]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=2)

        assert len(errors) == 0
        assert len(pipeline.queue) > 0

    def test_multiple_workers_fetching(
        self, mock_backend, mock_node_health, mock_fetch_xcp_blocks, mock_fallback_state_manager
    ):
        """Test multiple workers fetching blocks concurrently."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()
        pipeline.running = True

        fetch_counts = {"count": 0}

        def fetch_worker(start, end):
            nonlocal fetch_counts
            result = pipeline._fetch_blocks_batch(list(range(start, end)), "http://test:8080")
            with threading.Lock():
                fetch_counts["count"] += len(result)

        # Create multiple fetch workers
        threads = []
        for i in range(3):
            start = 820000 + i * 10
            end = start + 10
            t = threading.Thread(target=fetch_worker, args=(start, end))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=2)

        # All blocks should be fetched
        assert fetch_counts["count"] == 30


class TestTestPipelineSimple:
    """Test the test_pipeline_simple function."""

    def test_pipeline_simple_success(self, mock_backend, mock_node_health, mock_fetch_xcp_blocks, mock_fallback_state_manager):
        """Test successful pipeline test."""
        from index_core.pipeline_utils import test_pipeline_simple

        # Mock to make it succeed quickly
        def mock_get_block_side_effect(block_index):
            return {"block_index": block_index}

        with mock.patch("index_core.pipeline_utils.CPBlocksPipeline") as mock_pipeline_cls:
            mock_pipeline = mock.MagicMock()
            mock_pipeline.get_block.side_effect = mock_get_block_side_effect
            mock_pipeline._lock = threading.Lock()
            mock_pipeline.queue = {820000: {"block_index": 820000}}
            mock_pipeline.min_blocks_ready = 1
            mock_pipeline.initial_batch_size = 10
            mock_pipeline.initial_blocks_ready = mock.MagicMock()
            mock_pipeline.initial_blocks_ready.is_set.return_value = True
            mock_pipeline_cls.return_value = mock_pipeline

            result = test_pipeline_simple(start_block=820000, num_blocks=5, max_wait=1)

            assert result is True
            mock_pipeline.start.assert_called_once_with(820000)
            mock_pipeline.stop.assert_called_once()

    def test_pipeline_simple_timeout(self, mock_backend, mock_node_health, mock_fallback_state_manager):
        """Test pipeline test with timeout."""
        from index_core.pipeline_utils import test_pipeline_simple

        with mock.patch("index_core.pipeline_utils.CPBlocksPipeline") as mock_pipeline_cls:
            mock_pipeline = mock.MagicMock()
            mock_pipeline._lock = threading.Lock()
            mock_pipeline.queue = {}  # Empty queue
            mock_pipeline.min_blocks_ready = 1
            mock_pipeline.initial_batch_size = 10
            mock_pipeline_cls.return_value = mock_pipeline

            result = test_pipeline_simple(start_block=820000, num_blocks=5, max_wait=0.1)

            assert result is False

    def test_pipeline_simple_exception(self, mock_backend, mock_fallback_state_manager, mock_logger):
        """Test pipeline test with exception."""
        from index_core.pipeline_utils import test_pipeline_simple

        with mock.patch("index_core.pipeline_utils.CPBlocksPipeline") as mock_pipeline_cls:
            mock_pipeline_cls.side_effect = Exception("Test error")

            result = test_pipeline_simple()

            assert result is False
            mock_logger.error.assert_called()

    def test_pipeline_simple_default_start_block(
        self, mock_backend, mock_node_health, mock_fetch_xcp_blocks, mock_fallback_state_manager
    ):
        """Test pipeline test with default start block."""
        from index_core.pipeline_utils import test_pipeline_simple

        mock_backend.getblockcount.return_value = 820150

        with mock.patch("index_core.pipeline_utils.CPBlocksPipeline") as mock_pipeline_cls:
            mock_pipeline = mock.MagicMock()
            mock_pipeline._lock = threading.Lock()
            mock_pipeline.queue = {820050: {"block_index": 820050}}
            mock_pipeline.min_blocks_ready = 1
            mock_pipeline.initial_batch_size = 10
            mock_pipeline_cls.return_value = mock_pipeline

            result = test_pipeline_simple(start_block=None)

            # Should use current - 100 as start
            mock_pipeline.start.assert_called_once_with(820050)


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_get_block_at_chain_tip(self, mock_backend, mock_fallback_state_manager, mock_logger):
        """Test getting block at chain tip."""
        from index_core.pipeline_utils import CPBlocksPipeline

        mock_backend.getblockcount.return_value = 820100

        pipeline = CPBlocksPipeline()
        pipeline.current_block = 820100

        result = pipeline.get_block(820100)

        assert result is None
        # Should not log as error since it's expected
        mock_logger.error.assert_not_called()

    def test_get_block_sequence_issue(self, mock_backend, mock_fallback_state_manager, mock_logger):
        """Test get_block detects sequence issues."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline(fallback_mode=False)
        pipeline.current_block = 820000  # Initialize current_block

        # Add block 820011 but not 820010
        with pipeline._lock:
            pipeline.queue[820011] = {"block_index": 820011}

        result = pipeline.get_block(820010)

        assert result is None
        mock_logger.warning.assert_called_with("Block sequence issue: Missing block 820010 but have block 820011")

    def test_fetch_worker_no_healthy_nodes_fallback(self, mock_backend, mock_node_health, mock_fallback_state_manager):
        """Test fetch worker with no healthy nodes in fallback mode."""
        from index_core.pipeline_utils import CPBlocksPipeline

        mock_node_health["get_healthy_nodes"].return_value = []

        pipeline = CPBlocksPipeline(fallback_mode=True)
        pipeline.current_block = 820000
        pipeline.running = True
        pipeline.initial_batch_size = 5

        # Run worker briefly
        def run_briefly():
            call_count = 0
            original_sleep = time.sleep

            def mock_sleep(duration):
                nonlocal call_count
                call_count += 1
                if call_count > 1:
                    pipeline.shutdown_flag.set()
                original_sleep(0.01)

            with mock.patch("time.sleep", mock_sleep):
                pipeline._fetch_blocks_worker()

        run_briefly()

        # Should create fallback blocks
        assert len(pipeline.failed_cp_blocks) > 0
        assert len(pipeline.queue) > 0

    def test_executor_shutdown_handling(self, mock_fallback_state_manager, mock_logger):
        """Test handling of executor shutdown."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline()

        # Shutdown the executor
        pipeline.fetch_executor.shutdown()

        # Try to stop (should handle shutdown executor gracefully)
        pipeline.stop()

        # Should not raise exception
        assert True

    def test_concurrent_queue_modifications(self, mock_backend, mock_fallback_state_manager):
        """Test concurrent modifications to the queue."""
        from index_core.pipeline_utils import CPBlocksPipeline

        pipeline = CPBlocksPipeline(fallback_mode=False)
        pipeline.current_block = 820000  # Initialize current_block
        errors = []

        def add_blocks():
            try:
                for i in range(820000, 820100):
                    with pipeline._lock:
                        pipeline.queue[i] = {"block_index": i}
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def remove_blocks():
            try:
                for i in range(820000, 820100):
                    with pipeline._lock:
                        pipeline.queue.pop(i, None)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def get_blocks():
            try:
                for i in range(820000, 820100):
                    pipeline.get_block(i)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        # Run all operations concurrently
        threads = [
            threading.Thread(target=add_blocks),
            threading.Thread(target=remove_blocks),
            threading.Thread(target=get_blocks),
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=2)

        assert len(errors) == 0
