"""Manages snapshots of block hashes for reparse validation."""

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from dotenv import load_dotenv

import config
from index_core import check
from index_core.database_manager import DatabaseManager
from index_core.util import dhash_string, shash_string

logger = logging.getLogger(__name__)


# Define a Protocol for database connection
class DBConnection(Protocol):
    def cursor(self, *args: Any, **kwargs: Any) -> Any: ...

    def close(self) -> None: ...


class SnapshotManager:
    """Manages snapshots of block hashes for reparse validation."""

    def __init__(self, snapshot_path: str):
        self.snapshot_path = Path(snapshot_path)
        self._hashes: Optional[Dict] = None

    def compute_hash(self, data: Dict[str, Any]) -> str:
        """
        Compute a deterministic hash for block data using existing hash functions.
        Uses the same hashing logic as the consensus checks.
        """
        if "ledger_hash" in data:
            # For ledger hashes, use single SHA256 as per check.py
            content = json.dumps(data, sort_keys=True)
            return shash_string(content)
        else:
            # For other hashes (messages, txlist), use double SHA256
            content = json.dumps(data, sort_keys=True)
            return dhash_string(content)

    def compute_block_hash(self, block_data: Dict[str, Any], block_index: int) -> str:
        """
        Compute block hash using the consensus check logic.
        """
        # Get previous consensus hash from snapshot or database
        previous_hash = self.get_expected_hash(block_index - 1)

        # Use check.consensus_hash for validation
        computed_hash, _ = check.consensus_hash(
            db=None,  # We don't need db here since we're just computing
            block_index=block_index,
            field="txlist_hash",  # or appropriate field
            previous_consensus_hash=previous_hash,
            content=json.dumps(block_data, sort_keys=True),
        )
        return computed_hash

    def load_snapshot(self) -> Dict:
        """Load reference hashes from snapshot file."""
        if self._hashes is None:
            try:
                # Ensure parent directory exists
                self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)

                # Try to load existing snapshot
                if self.snapshot_path.exists():
                    with open(self.snapshot_path) as f:
                        self._hashes = json.load(f)
                    logger.info(f"Loaded {len(self._hashes)} reference hashes from {self.snapshot_path}")
                else:
                    logger.warning(f"No snapshot file found at {self.snapshot_path}, creating new")
                    self._hashes = {}
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding snapshot file: {e}")
                self._hashes = {}
            except Exception as e:
                logger.error(f"Error loading snapshot file: {e}")
                self._hashes = {}
        return self._hashes

    def save_snapshot(self, block_hashes: Dict[int, Dict[str, str]], metadata: Optional[Dict] = None) -> None:
        """Save block hashes to snapshot file."""
        if metadata is None:
            metadata = {}

        snapshot_data = {
            "metadata": metadata,
            "hashes": block_hashes,
        }

        with open(self.snapshot_path, "w") as f:
            json.dump(snapshot_data, f, indent=4)

        logger.info(f"Saved {len(block_hashes)} block hashes to {self.snapshot_path}")

    def get_expected_hash(self, block_index: int) -> Optional[Dict[str, str]]:
        """Get expected hash for a block from snapshot."""
        hashes = self.load_snapshot()
        if not hashes or "hashes" not in hashes:
            return None
        return hashes["hashes"].get(str(block_index))

    def validate_against_checkpoints(self, block_index: int, computed_hash: str) -> bool:
        """
        Validate computed hash against known checkpoints from check.py
        """
        if block_index in check.CHECKPOINTS_MAINNET:
            checkpoint = check.CHECKPOINTS_MAINNET[block_index]
            if computed_hash != checkpoint["txlist_hash"]:
                logger.error(
                    f"Hash mismatch at checkpoint {block_index}:\n"
                    f"  Computed: {computed_hash}\n"
                    f"  Expected: {checkpoint['txlist_hash']}"
                )
                return False
        return True

    def create_snapshot_from_db(self, db: DBConnection) -> Dict[str, Dict[str, str]]:
        """Create a new snapshot from current database contents."""
        logger.info("Creating new snapshot from database...")
        snapshot = {}

        try:
            cursor = db.cursor()

            # Get block range
            cursor.execute("SELECT MIN(block_index), MAX(block_index) FROM blocks")
            start_block, end_block = cursor.fetchone()

            if start_block is None or end_block is None:
                raise ValueError("No blocks found in database")

            # Start from genesis block
            genesis_block = config.CP_STAMP_GENESIS_BLOCK
            total_blocks = end_block - genesis_block + 1
            logger.info(f"Processing blocks from {genesis_block} to {end_block} (total: {total_blocks} blocks)")

            # Process blocks
            cursor.execute(
                """
                SELECT block_index, block_hash, messages_hash, txlist_hash, ledger_hash
                FROM blocks
                WHERE block_index BETWEEN %s AND %s
                ORDER BY block_index
                """,
                (genesis_block, end_block),
            )

            for row in cursor.fetchall():
                block_index = row[0]
                block_dict = {
                    "block_hash": row[1],
                    "messages_hash": row[2],
                    "txlist_hash": row[3],
                    "ledger_hash": row[4],
                }

                # Use checkpoint hash if available
                if block_index in check.CHECKPOINTS_MAINNET:
                    checkpoint = check.CHECKPOINTS_MAINNET[block_index]
                    block_dict["txlist_hash"] = checkpoint["txlist_hash"]
                    logger.debug(f"Used checkpoint hash for block {block_index}")

                # Store all hashes for the block
                snapshot[str(block_index)] = block_dict

                # Log progress every 10 blocks
                if block_index % 10 == 0:
                    progress = ((block_index - genesis_block) / total_blocks) * 100
                    logger.info(f"Processed block {block_index} ({progress:.2f}%)")

            logger.info(f"Successfully processed {len(snapshot)} blocks")
            return snapshot

        except Exception as e:
            logger.error(f"Error creating snapshot: {str(e)}")
            logger.debug("Exception details:", exc_info=True)
            raise

    def save_current_state(self, db: DBConnection) -> None:
        """
        Create and save a snapshot of the current database state.
        """
        try:
            snapshot = self.create_snapshot_from_db(db)
            self.save_snapshot(snapshot)
            logger.info("Successfully saved current state to snapshot")
        except Exception as e:
            logger.error(f"Failed to save current state: {str(e)}")
            raise


def main() -> None:
    """Command-line interface for snapshot management."""
    parser = argparse.ArgumentParser(description="Bitcoin Stamps Snapshot Manager")
    parser.add_argument("--snapshot-path", default="snapshots/reference_hashes.json", help="Path to snapshot file")
    parser.add_argument("--create", action="store_true", help="Create a new snapshot from current database state")
    parser.add_argument("--validate", action="store_true", help="Validate snapshot against checkpoints")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    try:
        # Load environment variables from .env file
        env_file = Path(__file__).parent.parent.parent.parent / ".env"
        if not env_file.exists():
            raise ValueError(f"Environment file not found at {env_file}")
        load_dotenv(env_file)

        # Log database connection info
        logger.info(f"Using database at {os.getenv('RDS_HOSTNAME')} with user {os.getenv('RDS_USER')}")

        # Initialize snapshot manager
        snapshot_manager = SnapshotManager(args.snapshot_path)

        if args.create:
            # Connect to database using DatabaseManager
            db_manager = DatabaseManager()
            db = db_manager.connect()

            try:
                # Create metadata for documentation purposes
                # local_metadata = {
                #     "genesis_block": config.CP_STAMP_GENESIS_BLOCK,
                #     "description": "Local snapshot for reparse validation",
                #     "version": "1.0.0",
                #     "database": os.getenv("RDS_HOSTNAME"),
                # }

                # Create and save snapshot
                snapshot_manager.save_current_state(db)
                logger.info(f"Successfully created snapshot at {args.snapshot_path}")

                # Validate genesis block
                genesis_hash = snapshot_manager.get_expected_hash(config.CP_STAMP_GENESIS_BLOCK)
                if genesis_hash:
                    logger.info(f"Genesis block hashes: {genesis_hash}")
                else:
                    logger.error("Genesis block not found in snapshot!")
            finally:
                db.close()

        if args.validate:
            # Load snapshot and validate against checkpoints
            snapshot = snapshot_manager.load_snapshot()
            if not snapshot:
                logger.error("No snapshot found to validate")
                return

            for block_index_str, hashes in snapshot.get("hashes", {}).items():
                block_index = int(block_index_str)
                if not snapshot_manager.validate_against_checkpoints(block_index, hashes["txlist_hash"]):
                    logger.error(f"Validation failed for block {block_index}")
                    return

            logger.info("Snapshot validation successful")

    except Exception as e:
        logger.error(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()
