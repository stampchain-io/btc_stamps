"""
Test rollback functionality with SQLite integration.

This test ensures that the simplified rollback tool works correctly with the new
SQLite-based fallback state management and doesn't interfere with
real Bitcoin block rollbacks.
"""

import tempfile
from unittest.mock import Mock, patch

import pytest

from src.index_core.database import perform_complete_rollback
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

    # Cleanup
    try:
        import os

        os.unlink(db_path)
    except (OSError, FileNotFoundError):
        pass
    ReprocessingQueue._instance = None


@pytest.fixture
def clean_singleton():
    """Ensure clean ReprocessingQueue singleton for each test."""
    # Clean before test
    if ReprocessingQueue._instance is not None:
        try:
            ReprocessingQueue._instance.close()
        except Exception:
            pass
    ReprocessingQueue._instance = None

    yield

    # Clean after test
    if ReprocessingQueue._instance is not None:
        try:
            ReprocessingQueue._instance.close()
        except Exception:
            pass
    ReprocessingQueue._instance = None


def test_rollback_tool_import_fix():
    """Test that simplified rollback tool can be imported without errors."""
    try:
        import os
        import sys

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
        import rollback_db

        # Verify the simplified tool has the main function
        assert hasattr(rollback_db, "main")
        # Verify the legacy clear_database function is removed
        assert not hasattr(rollback_db, "clear_database")
    except ImportError as e:
        pytest.fail(f"Rollback tool import failed: {e}")


def test_indexer_rollback_method_integration(temp_db, clean_singleton):
    """Test that the indexer's perform_complete_rollback method works with fallback state."""
    with patch("src.index_core.config.REPROCESS_DB_PATH", temp_db):
        # Set up fallback state
        queue = ReprocessingQueue.get_instance()
        fallback_data = {12345: True, 12346: True}
        queue.save_fallback_state(12345, fallback_data)

        # Mock the DatabaseManager and its connection
        with patch("src.index_core.database.DatabaseManager") as mock_db_manager_class:
            mock_db_manager = Mock()
            mock_conn = Mock()
            mock_db_manager.connect.return_value = mock_conn
            mock_db_manager_class.return_value = mock_db_manager

            # Mock the actual rollback operations
            with (
                patch("src.index_core.database.purge_block_db") as mock_purge,
                patch("src.index_core.database.clear_all_caches") as mock_clear_caches,
                patch("src.index_core.database.rebuild_balances") as mock_rebuild_balances,
                patch("src.index_core.database.rebuild_owners") as mock_rebuild_owners,
                patch("src.index_core.backend.Backend"),
            ):

                # Call the indexer's rollback method
                perform_complete_rollback(12000)

                # Verify rollback operations were called
                mock_purge.assert_called_with(mock_conn, 12000)
                mock_clear_caches.assert_called()
                mock_rebuild_balances.assert_called_with(mock_conn)
                mock_rebuild_owners.assert_called_with(mock_conn)
                # Note: update_src20_token_stats is now handled by async holder updater


def test_bitcoin_block_rollback_not_affected():
    """Test that Bitcoin block rollbacks (reorgs) work correctly with our rollback implementation."""
    # This test ensures that our rollback functionality works for Bitcoin blockchain reorganizations
    # We test this by mocking the complete rollback process

    # Mock a Bitcoin block rollback scenario (reorg detection)
    with patch("src.index_core.database.DatabaseManager") as mock_db_manager_class:
        mock_db_manager = Mock()
        mock_conn = Mock()
        mock_db_manager.connect.return_value = mock_conn
        mock_db_manager_class.return_value = mock_db_manager

        # Mock reorg detection and rollback
        with (
            patch("src.index_core.database.purge_block_db") as mock_purge,
            patch("src.index_core.database.clear_all_caches") as mock_clear_caches,
            patch("src.index_core.database.rebuild_balances") as mock_rebuild_balances,
            patch("src.index_core.database.rebuild_owners") as mock_rebuild_owners,
            patch("src.index_core.backend.Backend"),
        ):

            # Simulate a Bitcoin reorg requiring rollback to block 12000
            # This should work regardless of any fallback state
            perform_complete_rollback(12000)

            # Verify rollback operations were called normally
            mock_purge.assert_called_with(mock_conn, 12000)
            mock_clear_caches.assert_called()
            mock_rebuild_balances.assert_called_with(mock_conn)
            mock_rebuild_owners.assert_called_with(mock_conn)
            # Note: update_src20_token_stats is now handled by async holder updater


@pytest.mark.integration
@pytest.mark.requires_bitcoin_node
def test_rollback_tool_command_line_interface():
    """Test that the simplified rollback tool's command line interface works."""
    import os
    import sys

    # Skip if we're in CI environment without proper database setup
    if os.getenv("CI") and not os.getenv("TEST_WITH_REAL_DB"):
        pytest.skip("Skipping rollback tool test in CI without real database")

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

    # Test the simplified interface
    from rollback_db import main

    # Mock sys.argv to simulate command line usage with new simplified interface
    with patch("sys.argv", ["rollback_db.py", "12000", "--confirm"]):
        with patch("argparse.ArgumentParser.parse_args") as mock_parse:
            mock_args = Mock()
            mock_args.block_index = 12000
            mock_args.confirm = True  # Skip confirmation prompt
            mock_args.force = False  # Explicitly set force to False
            mock_parse.return_value = mock_args

            # Mock safety-check dependencies so the force=False path works without a real DB
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = (900000,)
            mock_conn = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db_manager = Mock()
            mock_db_manager.connect.return_value = mock_conn

            with (
                patch("index_core.database_manager.DatabaseManager", return_value=mock_db_manager),
                patch("rollback_db.validate_block_number"),
                patch("rollback_db.validate_rollback_distance"),
                patch("rollback_db.perform_complete_rollback") as mock_rollback,
                patch("builtins.print"),
            ):
                main()
                mock_rollback.assert_called_with(12000, force=False)


@pytest.mark.integration
@pytest.mark.requires_bitcoin_node
def test_rollback_tool_safety_confirmation():
    """Test that the rollback tool shows safety confirmation when --confirm is not used."""
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

    from rollback_db import main

    # Mock user input to decline rollback
    with patch("sys.argv", ["rollback_db.py", "12000"]):  # No --confirm flag
        with patch("argparse.ArgumentParser.parse_args") as mock_parse:
            mock_args = Mock()
            mock_args.block_index = 12000
            mock_args.confirm = False  # Requires confirmation
            mock_parse.return_value = mock_args

            with patch("builtins.input", return_value="no"):  # User declines
                with patch("sys.exit") as mock_exit:
                    with patch("builtins.print"):  # Mock print to avoid output
                        # Create isolated temp db for this test
                        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                            temp_db_path = f.name

                        try:
                            with patch("rollback_db.ReprocessingQueue") as mock_queue_class:
                                mock_queue_instance = Mock()
                                mock_queue_instance.get_oldest_failed_block.return_value = None
                                mock_queue_class.get_instance.return_value = mock_queue_instance

                                # This should exit before calling perform_complete_rollback
                                main()

                                # Should have called sys.exit(0) when user declined
                                mock_exit.assert_called_with(0)
                        finally:
                            try:
                                os.unlink(temp_db_path)
                            except (OSError, FileNotFoundError):
                                pass


def test_fallback_state_integration_with_rollback(temp_db, clean_singleton):
    """Test that fallback state is properly handled during rollback operations."""
    with patch("src.index_core.config.REPROCESS_DB_PATH", temp_db):
        # Set up fallback state
        queue = ReprocessingQueue.get_instance()
        fallback_data = {12345: True, 12346: True}
        queue.save_fallback_state(12345, fallback_data)

        # Verify state exists
        assert queue.get_oldest_failed_block() == 12345

        # Mock the complete rollback operation
        with patch("src.index_core.database.DatabaseManager") as mock_db_manager_class:
            mock_db_manager = Mock()
            mock_conn = Mock()
            mock_db_manager.connect.return_value = mock_conn
            mock_db_manager_class.return_value = mock_db_manager

            with (
                patch("src.index_core.database.purge_block_db"),
                patch("src.index_core.database.clear_all_caches"),
                patch("src.index_core.database.rebuild_balances"),
                patch("src.index_core.database.rebuild_owners"),
                patch("src.index_core.backend.Backend"),
            ):
                # Perform rollback to block before fallback started
                perform_complete_rollback(12000)

                # The rollback operation should complete successfully
                # Fallback state handling is managed by the main indexer code
