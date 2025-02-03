"""Validator for reparse operations."""

import logging
import os
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import MagicMock

from index_core.blocks import (
    BlockProcessor,
    backend_instance,
    create_check_hashes,
    fetch_xcp_blocks_concurrent,
    filter_block_transactions,
    process_tx,
)
from index_core.database_manager import DatabaseManager
from index_core.reparse.snapshot import SnapshotManager

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Base class for validation errors."""

    pass


class ReparseValidator:
    """Validator for reparse operations."""

    def __init__(self, snapshot_path: Optional[str] = None, db: Optional[DatabaseManager] = None):
        self.snapshot_path = snapshot_path or os.getenv("SNAPSHOT_PATH") or "snapshots/reference_hashes.json"
        Path(self.snapshot_path).parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_manager = SnapshotManager(self.snapshot_path)
        self.db = db  # Optional DB connection for creating reference hashes

    def compute_block_hashes(self, block_index: int, block_processor: Optional[BlockProcessor] = None) -> Dict[str, str]:
        """Compute hashes for a block using the same logic as production."""
        try:
            # Get block data from Bitcoin node
            block_hash = backend_instance.getblockhash(block_index)
            block_data = backend_instance.getblock(block_hash, 2)
            if not block_data:
                raise ValidationError(f"Failed to get block data for block {block_index}")

            # Get CP block data
            cp_blocks = fetch_xcp_blocks_concurrent(block_index, block_index)
            stamp_issuances = cp_blocks[block_index]["issuances"] if block_index in cp_blocks else []

            # Filter transactions
            txhash_list, raw_transactions = filter_block_transactions(block_data, stamp_issuances=stamp_issuances)

            # Process transactions using BlockProcessor if not provided
            if not block_processor:
                # Create a mock database for hash computation
                mock_db = MagicMock()
                mock_cursor = MagicMock()
                mock_cursor.fetchall.return_value = []
                mock_db.cursor.return_value = mock_cursor

                # Create a BlockProcessor instance
                block_processor = BlockProcessor(mock_db)

                # Process each transaction
                tx_results = []
                for tx_hash in txhash_list:
                    result = process_tx(mock_db, tx_hash, block_index, stamp_issuances, raw_transactions)
                    if result.data is not None:
                        result = result._replace(block_index=block_index, block_hash=block_hash, block_time=block_data["time"])
                        tx_results.append(result)

                # Process results using BlockProcessor
                block_processor.process_transaction_results(tx_results)

            # Get previous hashes from snapshot
            prev_hashes = self.snapshot_manager.get_expected_hash(block_index - 1) or {
                "ledger_hash": "0000000000000000000000000000000000000000000000000000000000000000",
                "txlist_hash": "0000000000000000000000000000000000000000000000000000000000000000",
                "messages_hash": "0000000000000000000000000000000000000000000000000000000000000000",
            }

            # Create a mock database for hash computation
            mock_db = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_db.cursor.return_value = mock_cursor

            # Compute hashes using existing create_check_hashes function
            new_ledger_hash, new_txlist_hash, new_messages_hash = create_check_hashes(
                mock_db,  # Use mock DB for hash computation
                block_index,
                block_processor.valid_stamps_in_block,
                "",  # Empty string for valid_src20_str as we're just validating
                txhash_list,
                prev_hashes["ledger_hash"],
                prev_hashes["txlist_hash"],
                prev_hashes["messages_hash"],
            )

            return {
                "block_hash": block_hash,
                "messages_hash": new_messages_hash,
                "txlist_hash": new_txlist_hash,
                "ledger_hash": new_ledger_hash,
            }

        except Exception as e:
            logger.error(f"Error computing hashes for block {block_index}: {e}")
            raise

    def validate_block(self, block_index: int) -> bool:
        """Validate a block by computing and comparing hashes."""
        try:
            # Compute hashes for the block
            computed_hashes = self.compute_block_hashes(block_index)

            # Get expected hash from snapshot
            expected_hashes = self.snapshot_manager.get_expected_hash(block_index)
            if not expected_hashes:
                raise ValidationError(f"No expected hashes found for block {block_index}")

            # Compare hashes
            for hash_type in ["messages_hash", "txlist_hash"]:  # Skip ledger_hash if empty
                if computed_hashes[hash_type] != expected_hashes[hash_type]:
                    logger.error(
                        f"Hash mismatch for block {block_index} ({hash_type}):\n"
                        f"  Computed: {computed_hashes[hash_type]}\n"
                        f"  Expected: {expected_hashes[hash_type]}"
                    )
                    return False

            # Only compare ledger_hash if it's not empty in the snapshot
            if expected_hashes["ledger_hash"]:
                if computed_hashes["ledger_hash"] != expected_hashes["ledger_hash"]:
                    logger.error(
                        f"Hash mismatch for block {block_index} (ledger_hash):\n"
                        f"  Computed: {computed_hashes['ledger_hash']}\n"
                        f"  Expected: {expected_hashes['ledger_hash']}"
                    )
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating block {block_index}: {e}")
            raise


def main() -> None:
    """Main entry point for the validator."""
    import argparse

    parser = argparse.ArgumentParser(description="Bitcoin Stamps Indexer Reparse Validator")
    parser.add_argument(
        "--snapshot-path",
        default=os.getenv("SNAPSHOT_PATH", "snapshots/reference_hashes.json"),
        help="Path to reference hash snapshot",
    )
    parser.add_argument("--block-index", type=int, help="Specific block to validate")

    args = parser.parse_args()

    try:
        validator = ReparseValidator(snapshot_path=args.snapshot_path)

        if args.block_index:
            if not validator.validate_block(args.block_index):
                logger.error("Validation failed")
                exit(1)
            logger.info("Block validated successfully")
        else:
            logger.error("Please specify a block to validate with --block-index")
            exit(1)

    except Exception as e:
        logger.error(f"Error during validation: {e}")
        exit(1)


if __name__ == "__main__":
    main()
