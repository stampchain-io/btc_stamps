#!/usr/bin/env python3
"""Test script for reparse functionality."""

import logging
import os
import sys
from pathlib import Path

## Add the src directory to the Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.append(str(src_path))

# Load environment variables from .env (e.g., RDS_HOSTNAME, RDS_USER, etc.)
try:
    from dotenv import load_dotenv

    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        logging.getLogger(__name__).info(f"Loaded environment from {env_file}")
except ImportError:
    logging.getLogger(__name__).warning("python-dotenv not installed; skipping .env load")

import sys
import types

# Stub boto3 to allow config import
sys.modules["boto3"] = types.ModuleType("boto3")
import config
from index_core.reparse.snapshot import SnapshotManager
from index_core.reparse.validator import ReparseValidator
from index_core.server import initialize_db

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    """Main test function."""
    # Increase log verbosity to see parsing details
    logging.getLogger().setLevel(logging.DEBUG)
    try:
        # Initialize database connection
        logger.info("Initializing database connection...")
        db = initialize_db()

        # Create snapshot manager
        snapshot_path = "snapshots/reference_hashes.json"
        logger.info(f"Creating snapshot manager with path: {snapshot_path}")
        snapshot_manager = SnapshotManager(snapshot_path)

        # Save current state
        logger.info("Saving current database state to snapshot...")
        snapshot_manager.save_current_state(db)

        # Create validator
        logger.info("Creating reparse validator...")
        validator = ReparseValidator(snapshot_path=snapshot_path)

        # Validate every block in the snapshot against computed hashes
        ref = snapshot_manager.load_snapshot().get("hashes", {})
        logger.info(f"Validating {len(ref)} blocks against snapshot...")
        for blk_str in sorted(ref.keys(), key=int):
            blk = int(blk_str)
            logger.info(f"Validating block {blk}...")
            try:
                if not validator.validate_block(blk):
                    raise RuntimeError(f"Validation failed for block {blk}")
            except Exception as e:
                logger.error(f"Error validating block {blk}: {e}")
                raise

    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
    finally:
        if "db" in locals():
            db.close()
            logger.info("Database connection closed")


if __name__ == "__main__":
    main()
