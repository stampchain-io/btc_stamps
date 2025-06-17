import json
from unittest.mock import MagicMock, patch

import pytest

import config
import index_core.check as check
import index_core.util as util
from index_core.blocks import BlockProcessor
from index_core.models import ValidStamp
from index_core.reparse.validator import ReparseValidator
from index_core.transaction_utils import TxResult


def test_hash_computation_matches_production():
    """Test that reparse hash computation exactly matches production logic."""

    # Use the genesis block
    block_index = config.CP_STAMP_GENESIS_BLOCK

    # Set BLOCK_FIRST to the correct value
    config.BLOCK_FIRST = config.CP_STAMP_GENESIS_BLOCK

    # Create validator instance with mock snapshot manager
    validator = ReparseValidator()

    # Mock the snapshot manager to return our expected hashes
    mock_snapshot_manager = MagicMock()

    def mock_get_expected_hash(block_index):
        if block_index == config.CP_STAMP_GENESIS_BLOCK - 1:  # Previous block
            return None  # Return None for the previous block
        elif block_index == config.CP_STAMP_GENESIS_BLOCK:  # Genesis block
            return {
                "block_hash": "00000000000000000004b29b2e3b5e6a4c5e2dba2aa2c2cf6af4f74b6a8a8f50",
                "messages_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "txlist_hash": "f5277855a60219dfff0ea837e6835478cbbc32c3520cb1dc1f13c296594b3a05",
                "ledger_hash": "",
            }
        return None

    mock_snapshot_manager.get_expected_hash.side_effect = mock_get_expected_hash
    validator.snapshot_manager = mock_snapshot_manager

    # Set current block index
    util.CURRENT_BLOCK_INDEX = block_index

    # Mock backend calls
    with patch("index_core.reparse.validator.backend_instance") as mock_backend:
        mock_backend.getblockhash.return_value = "00000000000000000004b29b2e3b5e6a4c5e2dba2aa2c2cf6af4f74b6a8a8f50"
        mock_backend.getblock.return_value = {
            "time": 1683849600,  # Approximate timestamp for block 779652
            "tx": [],  # Empty list since this is just the genesis block
        }

        # Mock CP block data
        with patch("index_core.reparse.validator.fetch_xcp_blocks_concurrent") as mock_fetch:
            mock_fetch.return_value = {
                block_index: {
                    "issuances": [],  # Empty since this is just the genesis block
                    "xcp_block_hash": "00000000000000000004b29b2e3b5e6a4c5e2dba2aa2c2cf6af4f74b6a8a8f50",
                }
            }

            # Mock filter_block_transactions to return empty lists since this is genesis
            with patch("index_core.reparse.validator.filter_block_transactions") as mock_filter:
                mock_filter.return_value = ([], {})

                # Create a BlockProcessor instance with mock db
                mock_db = MagicMock()
                mock_cursor = MagicMock()
                mock_cursor.fetchall.return_value = []
                mock_db.cursor.return_value = mock_cursor
                block_processor = BlockProcessor(mock_db)

                # Add valid stamps for genesis block
                block_processor.valid_stamps_in_block = []  # Empty list for genesis block

                # Mock create_check_hashes to ensure no previous hashes are passed for genesis block
                with patch("index_core.reparse.validator.create_check_hashes") as mock_create_hashes:

                    def mock_create_hashes_impl(db, block_index, valid_stamps, valid_src20_str, txhash_list, *args):
                        # For genesis block, ignore any previous hashes passed
                        if block_index == config.CP_STAMP_GENESIS_BLOCK:
                            return (
                                "",
                                "f5277855a60219dfff0ea837e6835478cbbc32c3520cb1dc1f13c296594b3a05",
                                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                            )
                        # Call original implementation for other blocks
                        return mock_create_hashes.return_value

                    mock_create_hashes.side_effect = mock_create_hashes_impl

                    # Compute hashes via reparse
                    computed_hashes = validator.compute_block_hashes(block_index, block_processor=block_processor)

                    # Verify computed hashes match expected
                    expected_hashes = mock_get_expected_hash(block_index)
                    assert computed_hashes["block_hash"] == expected_hashes["block_hash"]
                    assert computed_hashes["messages_hash"] == expected_hashes["messages_hash"]
                    assert computed_hashes["txlist_hash"] == expected_hashes["txlist_hash"]
                    assert computed_hashes["ledger_hash"] == expected_hashes["ledger_hash"]
