#!/usr/bin/env python3
"""Test script for reparse functionality."""

import logging
import os
import sys
from pathlib import Path

# Add the src directory to the Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.append(str(src_path))

import config
from index_core.reparse.snapshot import SnapshotManager
from index_core.reparse.validator import ReparseValidator
from index_core.server import initialize_db

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    """Main test function."""
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

        # Test validation on genesis block
        genesis_block = config.CP_STAMP_GENESIS_BLOCK
        logger.info(f"Testing validation on genesis block {genesis_block}...")

        try:
            is_valid = validator.validate_block(genesis_block)
            if is_valid:
                logger.info(f"✅ Block {genesis_block} validated successfully!")
            else:
                logger.error(f"❌ Block {genesis_block} validation failed!")
        except Exception as e:
            logger.error(f"Error validating block {genesis_block}: {e}")
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
