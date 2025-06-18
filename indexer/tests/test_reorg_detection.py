import logging
import sys
import unittest
from unittest.mock import ANY, MagicMock, patch

import pytest

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", stream=sys.stdout)
logger = logging.getLogger("test_reorg_detection")

import config

# Import the code being tested
from index_core import blocks, util

# Mark all tests in this file as integration tests due to complex blockchain reorg logic
pytestmark = pytest.mark.integration


class TestReorgDetection(unittest.TestCase):
    """A minimal test focusing only on reorg detection."""

    def setUp(self):
        # Save original values to restore later
        self.original_block_index = util.CURRENT_BLOCK_INDEX

        # Create mock database connection
        self.mock_db = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_db.cursor.return_value = self.mock_cursor
        self.mock_cursor.__enter__.return_value = self.mock_cursor

        # Set up basic block state
        self.current_block = 105
        util.CURRENT_BLOCK_INDEX = self.current_block

        # Block hashes
        self.block_103_hash = "0000...103"
        self.block_104_orig_hash = "0000...104_orig"
        self.block_104_new_hash = "0000...104_new"  # Different hash - reorg happened!
        self.block_105_orig_hash = "0000...105_orig"
        self.block_105_new_hash = "0000...105_new"

        # Database state for blocks already processed
        self.db_blocks = {
            104: (104, self.block_104_orig_hash, 1234567890, self.block_103_hash, 1, 1),
            105: (105, self.block_105_orig_hash, 1234567890, self.block_104_orig_hash, 1, 1),
        }

        # Override fetchall to return proper block data
        def mock_fetchall_side_effect():
            query = self.mock_cursor.execute.call_args[0][0].lower()
            if "from blocks where block_index" in query:
                params = self.mock_cursor.execute.call_args[0][1]
                block_index = params[0]
                logger.debug(f"DB query for block_index={block_index}")
                if block_index in self.db_blocks:
                    return [self.db_blocks[block_index]]
            return []

        self.mock_cursor.fetchall.side_effect = mock_fetchall_side_effect

        # Patch all blocks.py functions we need to mock
        self.patches = []

        # Mock backend to return different hash for same block index
        backend_patch = patch("index_core.blocks.backend_instance")
        self.mock_backend = backend_patch.start()
        self.patches.append(backend_patch)

        # Mock is_prev_block_parsed to always return True
        prev_parsed_patch = patch("index_core.blocks.is_prev_block_parsed", return_value=True)
        self.mock_prev_parsed = prev_parsed_patch.start()
        self.patches.append(prev_parsed_patch)

        # Mock rollback_to_block
        rollback_patch = patch("index_core.blocks.rollback_to_block")
        self.mock_rollback = rollback_patch.start()
        self.mock_rollback.return_value = 103  # Rollback to block 103
        self.patches.append(rollback_patch)

        # Mock functions that would call other services
        patches_to_start = [
            patch(
                "index_core.blocks.fetch_xcp_blocks_concurrent",
                return_value={106: {"block_hash": "hash_106", "xcp_block_hash": "hash_106", "issuances": []}},
            ),
            patch("index_core.blocks.CPBlocksPipeline"),
            patch("index_core.blocks.insert_block"),
            patch("index_core.blocks.BlockProcessor"),
            patch("index_core.blocks.create_check_hashes", return_value=("h1", "h2", "h3")),
            patch("index_core.blocks.commit_and_update_block", return_value=106),
            # Mock initialize to avoid the "First block is not block 0" error
            patch("index_core.blocks.initialize"),
            patch("index_core.blocks.rebuild_balances"),
            patch("index_core.blocks.rebuild_owners"),
            patch("index_core.blocks.update_src20_token_stats"),
            patch("index_core.blocks.process_tx"),
            patch("index_core.blocks.log_block_info"),
            patch("index_core.blocks.filter_block_transactions", return_value=(["tx1"], {"tx1": "hex1"})),
            patch("index_core.blocks.find_common_ancestor_with_xcp", return_value=103),
            patch("index_core.blocks.next_tx_index", return_value=1),
            patch("index_core.blocks.Profiler"),
            patch("index_core.blocks.ZMQNotifier"),
        ]

        # Start all patches
        for p in patches_to_start:
            p.start()
            self.patches.append(p)

    def tearDown(self):
        # Stop all patches
        for p in self.patches:
            p.stop()

        # Restore original values
        util.CURRENT_BLOCK_INDEX = self.original_block_index

    def test_reorg_detected_triggers_rollback(self):
        """Test that a blockchain reorganization is correctly detected and triggers a rollback."""
        # Configure backend to report a different hash than what's in our DB
        self.mock_backend.getblockcount.return_value = 106  # New tip available

        # Configure getblockhash to return NEW hashes
        self.mock_backend.getblockhash.side_effect = lambda idx: {
            103: self.block_103_hash,  # Common ancestor - same hash
            104: self.block_104_new_hash,  # Different hash - REORG!
            105: self.block_105_new_hash,  # Different hash - REORG!
            106: "hash_106",  # New block
        }.get(idx, f"hash_{idx}")

        # Configure getblockheader to return headers that link back to our chain
        self.mock_backend.getblockheader.side_effect = lambda block_hash: {
            self.block_104_new_hash: {"previousblockhash": self.block_103_hash},
            self.block_105_new_hash: {"previousblockhash": self.block_104_new_hash},
            "hash_106": {"previousblockhash": self.block_105_new_hash},
        }.get(block_hash, {"previousblockhash": "unknown"})

        # Configure get_tx_list to return valid output
        self.mock_backend.get_tx_list.return_value = ([], {}, 1234567890, "prev_hash", 1)

        # Set up the poll interval for faster testing
        original_poll_interval = config.BACKEND_POLL_INTERVAL
        config.BACKEND_POLL_INTERVAL = 0.01

        try:
            # Call blocks.follow which should detect the reorg
            logger.debug("Starting blocks.follow() call")
            blocks.follow(self.mock_db, single_block=True, cp_pipeline=False, zmq_enabled=False, update_cpids=False)
            logger.debug("Finished blocks.follow() call")

            # Verify rollback was called with correct parameters
            self.mock_rollback.assert_called_once()

            # Check rollback target is correct (should be less than or equal to block 104)
            rollback_args = self.mock_rollback.call_args[0]
            self.assertEqual(rollback_args[0], self.mock_db)  # First arg should be DB
            self.assertLessEqual(rollback_args[1], 104)  # Target block should be 104 or earlier

            # Check reason contains reorg information
            reason = rollback_args[2]
            self.assertIn("reorganization", reason.lower())

        finally:
            # Restore original poll interval
            config.BACKEND_POLL_INTERVAL = original_poll_interval


if __name__ == "__main__":
    unittest.main()
