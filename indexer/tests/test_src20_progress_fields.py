#!/usr/bin/env python3
"""
Test SRC-20 progress percentage and total minted field calculations.
"""

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from index_core.src20_holder_updater import SRC20HolderCountUpdater


class TestSRC20ProgressFields:
    """Test progress percentage and total minted calculations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_db_manager = MagicMock()
        self.holder_updater = SRC20HolderCountUpdater(db_manager=self.mock_db_manager)

    def test_progress_calculation_normal_token(self):
        """Test progress calculation for a normal token."""
        # Mock data: Token with max supply of 1000, 750 minted
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1

        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        self.mock_db_manager.connect.return_value = mock_connection

        # Track a token and update
        self.holder_updater.track_affected_token("TEST")
        updated = self.holder_updater.update_holder_counts(900000, db_connection=mock_connection)

        # Verify the SQL includes progress calculation
        assert mock_cursor.execute.called
        # Check all execute calls to find the one with progress calculation
        sql_calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
        progress_sql = next(
            (sql for sql in sql_calls if "ROUND(COALESCE(SUM(b.amt), 0) / NULLIF(d.max, 0) * 100, 2)" in sql), None
        )
        assert progress_sql is not None, "Progress calculation SQL not found"
        assert "progress_percentage" in progress_sql
        assert "total_minted" in progress_sql

    def test_progress_calculation_zero_supply(self):
        """Test progress calculation for token with zero max supply."""
        # This should result in 0% progress to avoid division by zero
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1

        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        self.mock_db_manager.connect.return_value = mock_connection

        self.holder_updater.track_affected_token("ZERO")
        self.holder_updater.update_holder_counts(900000, db_connection=mock_connection)

        # Verify NULLIF is used to handle zero division
        # Check all execute calls to find the one with NULLIF
        sql_calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
        nullif_sql = next((sql for sql in sql_calls if "NULLIF(d.max, 0)" in sql), None)
        assert nullif_sql is not None, "NULLIF SQL not found for zero division protection"

    def test_force_mode_updates_all(self):
        """Test that force mode updates all tokens."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 10

        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        self.mock_db_manager.connect.return_value = mock_connection

        # Force update without tracking specific tokens
        updated = self.holder_updater.update_holder_counts(900000, force=True)

        assert updated == 10
        # Verify it updates all tokens, not just tracked ones
        sql_call = mock_cursor.execute.call_args[0][0]
        assert "WHERE smd.holder_count IS NULL" in sql_call or "OR smd.total_minted IS NULL" in sql_call

    def test_batch_processing(self):
        """Test that large numbers of tokens are processed in batches."""
        mock_cursor = MagicMock()
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        self.mock_db_manager.connect.return_value = mock_connection

        # Track more than batch size (50) tokens
        for i in range(60):
            self.holder_updater.track_affected_token(f"TOKEN{i}")

        self.holder_updater.update_holder_counts(900000, db_connection=mock_connection)

        # Should have multiple execute calls for batches
        assert mock_cursor.execute.call_count >= 2  # At least 2 batches

    def test_market_data_entry_creation_on_deploy(self):
        """Test that market data entries are created for new DEPLOY operations."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # No existing entry

        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        self.mock_db_manager.connect.return_value = mock_connection

        # Ensure market data exists for a new token
        self.holder_updater.ensure_market_data_exists("NEWTOKEN", db_connection=mock_connection)

        # Verify INSERT was called
        assert mock_cursor.execute.call_count == 2  # SELECT + INSERT
        insert_call = mock_cursor.execute.call_args_list[1][0][0]
        assert "INSERT INTO src20_market_data" in insert_call
        assert "holder_count" in insert_call
        assert "ON DUPLICATE KEY UPDATE" in insert_call

    def test_clear_tracked_tokens(self):
        """Test clearing tracked tokens."""
        # Track some tokens
        self.holder_updater.track_affected_token("TEST1")
        self.holder_updater.track_affected_token("TEST2")

        assert self.holder_updater.get_affected_token_count() == 2

        # Clear
        self.holder_updater.clear()

        assert self.holder_updater.get_affected_token_count() == 0

    def test_progress_percentage_precision(self):
        """Test that progress percentage is calculated with proper precision."""
        # Mock data to simulate 66.666... which should round to 66.67
        mock_cursor = MagicMock()
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        self.mock_db_manager.connect.return_value = mock_connection

        self.holder_updater.track_affected_token("PRECISION")
        self.holder_updater.update_holder_counts(900000, db_connection=mock_connection)

        # Verify ROUND(..., 2) is used for 2 decimal places in the UPDATE query
        sql_calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
        # Look specifically for the UPDATE query with progress calculation
        update_sql = next(
            (sql for sql in sql_calls if "UPDATE src20_market_data" in sql and "progress_percentage" in sql), None
        )
        assert update_sql is not None, "UPDATE query with progress_percentage not found"
        # The ROUND function is in the subquery
        assert (
            "ROUND(COALESCE(SUM(b.amt), 0) / NULLIF(d.max, 0) * 100, 2)" in update_sql
        ), "ROUND(..., 2) not found in progress calculation"

    @patch("index_core.src20_holder_updater.logger")
    def test_error_handling(self, mock_logger):
        """Test that errors don't crash the indexer."""
        mock_connection = MagicMock()
        mock_connection.cursor.side_effect = Exception("Database error")

        self.mock_db_manager.connect.return_value = mock_connection

        self.holder_updater.track_affected_token("ERROR")

        # Should raise but log the error
        with pytest.raises(Exception):
            self.holder_updater.update_holder_counts(900000, db_connection=mock_connection)

        mock_logger.error.assert_called()

    def test_tokens_with_no_balances(self):
        """Test handling of tokens with no balance entries."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1

        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        self.mock_db_manager.connect.return_value = mock_connection

        self.holder_updater.track_affected_token("NOBALANCE")
        self.holder_updater.update_holder_counts(900000, db_connection=mock_connection)

        # Should handle tokens with no balances (0 minted, 0% progress)
        sql_calls = [call[0][0] for call in mock_cursor.execute.call_args_list]

        # Check that the zero balance update is included
        zero_balance_update = any(
            "smd.total_minted = 0" in sql and "smd.progress_percentage = 0.00" in sql for sql in sql_calls
        )
        assert zero_balance_update


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
