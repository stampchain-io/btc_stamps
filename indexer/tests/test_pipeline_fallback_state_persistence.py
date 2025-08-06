"""
Test fallback state persistence in CPBlocksPipeline with SQLite integration.

This test verifies that the restored state manager functionality properly
persists and loads fallback state across pipeline restarts.
"""

import tempfile
import threading
import time
from unittest.mock import patch

import pytest

from src.index_core.pipeline_utils import CPBlocksPipeline
from src.index_core.reprocessing_queue import ReprocessingQueue


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Reset singleton instance for clean test
    if ReprocessingQueue._instance is not None:
        try:
            ReprocessingQueue._instance.close()
        except Exception:
            pass
    ReprocessingQueue._instance = None

    yield db_path

    # Cleanup - close any existing instance first
    if ReprocessingQueue._instance is not None:
        try:
            ReprocessingQueue._instance.close()
        except Exception:
            pass
    ReprocessingQueue._instance = None

    try:
        import os

        os.unlink(db_path)
    except (OSError, FileNotFoundError):
        pass


@pytest.fixture
def mock_backend():
    """Mock the backend instance used by pipeline."""
    with patch("src.index_core.pipeline_utils.backend_instance") as mock:
        mock.getblockcount.return_value = 850000
        mock.invalidate_blockcount_cache.return_value = None
        yield mock


@pytest.fixture
def mock_node_health():
    """Mock node health functions."""
    with patch("src.index_core.pipeline_utils.update_healthy_nodes") as mock_update, patch(
        "src.index_core.pipeline_utils.get_healthy_nodes"
    ) as mock_get:
        mock_update.return_value = None
        mock_get.return_value = []  # No healthy nodes to trigger fallback
        yield mock_update, mock_get


def test_fallback_state_persistence_initialization(temp_db, mock_backend, mock_node_health):
    """Test that pipeline correctly initializes state manager and loads persisted fallback state."""

    # First, manually create some fallback state in the database
    with patch("src.index_core.config.REPROCESS_DB_PATH", temp_db):
        queue = ReprocessingQueue.get_instance()
        fallback_data = {12345: True, 12346: True, 12347: True}
        queue.save_fallback_state(12345, fallback_data)

    # Reset singleton to force re-initialization
    ReprocessingQueue._instance = None

    # Create pipeline with fallback mode enabled
    with patch("src.index_core.config.REPROCESS_DB_PATH", temp_db):
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)

    # Verify state manager is initialized
    assert pipeline.state_manager is not None
    assert isinstance(pipeline.state_manager, ReprocessingQueue)

    # Verify fallback state was loaded from persistence
    assert pipeline.fallback_started_at == 12345
    assert pipeline.failed_cp_blocks == {12345, 12346, 12347}


def test_fallback_state_persistence_disabled_when_fallback_mode_false(temp_db, mock_backend):
    """Test that state manager is None when fallback_mode is False."""

    with patch("src.index_core.config.REPROCESS_DB_PATH", temp_db):
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=False)

    # Verify state manager is not initialized
    assert pipeline.state_manager is None
    assert pipeline.fallback_started_at is None
    assert pipeline.failed_cp_blocks == set()


def test_fallback_state_save_on_enter_fallback_mode(temp_db, mock_backend, mock_node_health):
    """Test that fallback state is saved when entering fallback mode."""

    with patch("src.index_core.config.REPROCESS_DB_PATH", temp_db):
        # Ensure clean database - clear any existing fallback states
        queue = ReprocessingQueue.get_instance()
        queue.clear_all_fallbacks()

        # Reset singleton to ensure clean initialization
        ReprocessingQueue._instance = None

        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)

        # Verify clean start (no previous state loaded)
        assert pipeline.fallback_started_at is None

        # Mock backend to simulate being near chain tip
        with patch("src.index_core.blocks.backend_instance") as mock_backend_instance:
            mock_backend_instance.getblockcount.return_value = 12400  # 50 blocks ahead

            # Simulate entering fallback mode
            pipeline.current_block = 12350
            pipeline._enter_fallback_mode()

            # Verify state was saved
            assert pipeline.fallback_started_at == 12350

        # Verify state was persisted to SQLite
        queue = ReprocessingQueue.get_instance()
        loaded_state = queue.load_fallback_state(12350)
        assert loaded_state == {12350: True}  # New normalized structure preserves integer keys


def test_fallback_state_clear_after_rollback(temp_db, mock_backend, mock_node_health):
    """Test that fallback state is cleared after successful rollback."""

    # Create initial fallback state
    with patch("src.index_core.config.REPROCESS_DB_PATH", temp_db):
        queue = ReprocessingQueue.get_instance()
        fallback_data = {12345: True}
        queue.save_fallback_state(12345, fallback_data)

    # Reset singleton
    ReprocessingQueue._instance = None

    # Mock the rollback function and healthy nodes after rollback
    with patch("src.index_core.config.REPROCESS_DB_PATH", temp_db), patch.object(
        CPBlocksPipeline, "_perform_startup_rollback"
    ) as mock_rollback:

        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)

        # Verify initial state was loaded
        assert pipeline.fallback_started_at == 12345

        # Mock healthy nodes being available after rollback to prevent re-entering fallback
        mock_node_health[1].return_value = ["http://healthy-node:4000"]  # mock_get returns healthy nodes

        # Simulate starting the pipeline (which should trigger rollback)
        with patch("src.config.CP_STAMP_GENESIS_BLOCK", 0):
            pipeline.start(12340)

        # Verify rollback was called
        mock_rollback.assert_called_once_with(12345)

        # Verify state was cleared (should remain cleared since we have healthy nodes now)
        assert pipeline.fallback_started_at is None
        assert pipeline.failed_cp_blocks == set()

        # Verify state was cleared from SQLite
        queue = ReprocessingQueue.get_instance()
        loaded_state = queue.load_fallback_state(12345)
        assert loaded_state is None


def test_fallback_state_no_persistence_when_no_state_manager(mock_backend, mock_node_health):
    """Test that no errors occur when state manager is None."""

    pipeline = CPBlocksPipeline(
        max_queue_size=10, target_queue_size=5, fallback_mode=False  # This will set state_manager to None
    )

    # Verify state manager is None
    assert pipeline.state_manager is None

    # Mock backend to simulate being near chain tip
    with patch("src.index_core.blocks.backend_instance") as mock_backend_instance:
        mock_backend_instance.getblockcount.return_value = 12400  # 50 blocks ahead

        # Simulate entering fallback mode (should not crash)
        pipeline.current_block = 12350
        pipeline._enter_fallback_mode()

        # Verify fallback mode was activated but no persistence occurred
        assert pipeline.fallback_started_at == 12350
        assert pipeline.fallback_mode is True  # Should be enabled during runtime


def test_fallback_state_empty_database_initialization(temp_db, mock_backend, mock_node_health):
    """Test initialization with empty database (no previous fallback state)."""

    with patch("src.index_core.config.REPROCESS_DB_PATH", temp_db):
        # Ensure truly clean database
        queue = ReprocessingQueue.get_instance()
        queue.clear_all_fallbacks()

        # Reset singleton to ensure clean initialization
        ReprocessingQueue._instance = None

        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)

    # Verify state manager is initialized but no fallback state loaded
    assert pipeline.state_manager is not None
    assert pipeline.fallback_started_at is None
    assert pipeline.failed_cp_blocks == set()


@pytest.mark.asyncio
async def test_fallback_state_thread_safety(temp_db, mock_backend, mock_node_health):
    """Test that fallback state operations are thread-safe."""

    with patch("src.index_core.config.REPROCESS_DB_PATH", temp_db):
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)

        # Mock backend to simulate being near chain tip
        with patch("src.index_core.blocks.backend_instance") as mock_backend_instance:
            mock_backend_instance.getblockcount.return_value = 12400  # 50 blocks ahead

            # Function to simulate concurrent fallback state operations
            def save_fallback_state(block_num):
                pipeline.current_block = block_num
                pipeline._enter_fallback_mode()
                time.sleep(0.01)  # Small delay to increase chance of race conditions

            # Create multiple threads that try to save fallback state
            threads = []
            for i in range(5):
                thread = threading.Thread(target=save_fallback_state, args=(12350 + i,))
                threads.append(thread)

            # Start all threads
            for thread in threads:
                thread.start()

            # Wait for all threads to complete
            for thread in threads:
                thread.join()

            # Verify that at least one fallback state was saved successfully
            # (Due to the nature of the test, only one should succeed due to the check for existing fallback_started_at)
            assert pipeline.fallback_started_at is not None

        # Verify state was persisted to SQLite
        queue = ReprocessingQueue.get_instance()
        loaded_state = queue.load_fallback_state(pipeline.fallback_started_at)
        assert loaded_state is not None


if __name__ == "__main__":
    pytest.main([__file__])
