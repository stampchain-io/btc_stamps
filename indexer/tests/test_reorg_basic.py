import time
import unittest
from unittest.mock import MagicMock, patch

import pytest

import config

# Import the minimal required components
from index_core import blocks, util

# Mark all tests in this file as integration tests due to complex blockchain logic
pytestmark = pytest.mark.integration


class TestReorgBasic(unittest.TestCase):
    """A simple, focused test for blockchain reorganization detection."""

    def setUp(self):
        # Simplified mock setup
        self.mock_db = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_db.cursor.return_value = self.mock_cursor
        self.mock_cursor.__enter__.return_value = self.mock_cursor

        # Mock cursor description for dict creation
        self.mock_cursor.description = [
            ("block_index",),
            ("block_hash",),
            ("block_time",),
            ("previous_block_hash",),
            ("difficulty",),
            ("parsed",),
        ]

        # Set up blockchain state
        self.block_103_hash = "hash_103"
        self.block_104_orig_hash = "hash_104_orig"
        self.block_104_new_hash = "hash_104_new"
        self.block_105_orig_hash = "hash_105_orig"
        self.block_105_new_hash = "hash_105_new"

        # Patch backend instance
        self.patcher_backend = patch("index_core.blocks.backend_instance")
        self.mock_backend = self.patcher_backend.start()

        # Setup minimal required mocks
        self.patcher_rollback = patch("index_core.blocks.rollback_to_block")
        self.mock_rollback = self.patcher_rollback.start()
        self.mock_rollback.return_value = 103  # Return rollback target

        # Setup mock database state
        self.db_state = {
            103: (103, self.block_103_hash, 0, "prev_hash", 1, 1),
            104: (104, self.block_104_orig_hash, 0, self.block_103_hash, 1, 1),
            105: (105, self.block_105_orig_hash, 0, self.block_104_orig_hash, 1, 1),
        }

        # Patch config values
        self.original_BACKEND_POLL_INTERVAL = config.BACKEND_POLL_INTERVAL
        config.BACKEND_POLL_INTERVAL = 0.01
        self.original_BLOCK_FIRST = config.BLOCK_FIRST
        config.BLOCK_FIRST = 100

        # Reset CURRENT_BLOCK_INDEX
        util.CURRENT_BLOCK_INDEX = 104  # Already processed up to 104, will start at 105

    def tearDown(self):
        self.patcher_backend.stop()
        self.patcher_rollback.stop()

        # Restore config values
        config.BACKEND_POLL_INTERVAL = self.original_BACKEND_POLL_INTERVAL
        config.BLOCK_FIRST = self.original_BLOCK_FIRST

    def test_reorg_detected_and_rollback_called(self):
        """Test that a reorg is detected by hash mismatch and rollback is called."""

        # Setup database mock to return our blockchain state
        def execute_side_effect(query, params):
            # Store the query params for fetchall to use
            self.mock_cursor._last_params = params

        def fetchall_side_effect():
            if hasattr(self.mock_cursor, "_last_params") and self.mock_cursor._last_params:
                block_index = self.mock_cursor._last_params[0]
                if block_index in self.db_state:
                    return [self.db_state[block_index]]
            return []

        self.mock_cursor.execute = MagicMock(side_effect=execute_side_effect)
        self.mock_cursor.fetchall = MagicMock(side_effect=fetchall_side_effect)

        # Configure backend mock to return different hashes (simulating reorg)
        # We'll change the hash dynamically to simulate a reorg during processing
        self.hash_call_count = 0

        def dynamic_hash_side_effect(idx):
            self.hash_call_count += 1
            hashes = {
                103: self.block_103_hash,  # Same hash (common ancestor)
                104: self.block_104_orig_hash,  # Always return original for 104
                105: self.block_105_new_hash,  # Different hash (reorged block)
            }
            return hashes.get(idx, f"hash_{idx}")

        self.mock_backend.getblockcount.return_value = 105  # Current tip is 105
        self.mock_backend.getblockhash.side_effect = dynamic_hash_side_effect

        # Setup block headers for mismatch detection
        self.mock_backend.getblockheader.side_effect = lambda block_hash: {
            self.block_104_orig_hash: {"previousblockhash": self.block_103_hash},
            self.block_105_new_hash: {"previousblockhash": self.block_104_new_hash},  # This will cause the mismatch
        }.get(block_hash, {"previousblockhash": f"prev_{block_hash}"})

        # Setup get_tx_list on the backend mock
        self.mock_backend.get_tx_list.return_value = ([], {}, time.time(), "prev_hash", 1)

        # Setup other required mocks to avoid errors
        with patch("index_core.blocks.is_prev_block_parsed", return_value=True), patch(
            "index_core.blocks.fetch_xcp_blocks_concurrent",
            return_value={105: {"issuances": [], "xcp_block_hash": self.block_105_new_hash}},
        ), patch("index_core.blocks.insert_block"), patch("index_core.blocks.initialize"), patch(
            "index_core.blocks.commit_and_update_block", return_value=105
        ), patch(
            "index_core.blocks.create_check_hashes", return_value=("h1", "h2", "h3")
        ), patch(
            "index_core.blocks.rebuild_balances"
        ), patch(
            "index_core.blocks.rebuild_owners"
        ), patch(
            "index_core.blocks.update_src20_token_stats"
        ), patch(
            "index_core.blocks.next_tx_index", return_value=1
        ), patch(
            "index_core.blocks.filter_block_transactions", return_value=([], {})
        ):

            # Call the function being tested - this should detect a reorg
            blocks.follow(
                self.mock_db, single_block=True, cp_pipeline=False, zmq_enabled=False, update_cpids=False, reparse_mode=False
            )

            # Assert that rollback was called with the correct params
            self.mock_rollback.assert_called_once()
            # Rollback should target block 103 (before the reorg)
            self.assertIn(103, [call_args[0][1] for call_args in self.mock_rollback.call_args_list])
            # Verify reason contains reorg information
            reason = self.mock_rollback.call_args[0][2]
            self.assertIn("Chain reorganization", reason)


if __name__ == "__main__":
    unittest.main()
