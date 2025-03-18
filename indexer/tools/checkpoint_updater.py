#!/usr/bin/env python3
"""
Simple script to update CHECKPOINTS_MAINNET in check.py with the latest
ledger_hash and txlist_hash values from the database.
"""
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import dotenv

# Set up the path so we can import our modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Load environment variables from .env
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
if dotenv_path.exists():
    dotenv.load_dotenv(str(dotenv_path))
    print(f"Loaded environment from {dotenv_path}")
else:
    print(f"Warning: No .env file found at {dotenv_path}")

import config
from index_core.database_manager import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_latest_block() -> int:
    """Get the latest block height from the database"""
    db_manager = DatabaseManager()
    try:
        conn = db_manager.connect()
        with conn.cursor() as cursor:
            cursor.execute("SELECT MAX(block_index) FROM blocks")
            result = cursor.fetchone()
            if result and result[0]:
                return int(result[0])
            else:
                logger.warning("Could not get latest block from database")
                return 0
    except Exception as e:
        logger.error(f"Database error: {e}")
        return 0


def get_checkpoint_hashes(block_height: int) -> Optional[Tuple[str, str]]:
    """Get ledger_hash and txlist_hash for a specific block height"""
    db_manager = DatabaseManager()
    try:
        conn = db_manager.connect()
        with conn.cursor() as cursor:
            cursor.execute("SELECT ledger_hash, txlist_hash FROM blocks WHERE block_index = %s", (block_height,))
            result = cursor.fetchone()
            if result:
                ledger_hash, txlist_hash = result
                # If the ledger_hash or txlist_hash is None, return an empty string
                return (ledger_hash or "", txlist_hash or "")
            logger.warning(f"No hash values found for block {block_height}")
            return None
    except Exception as e:
        logger.error(f"Database error for block {block_height}: {e}")
        return None


def calculate_5000_blocks(latest_block: int) -> List[int]:
    """Calculate blocks at 5000-block intervals"""
    # Round up genesis block to the nearest 5000
    genesis = config.CP_STAMP_GENESIS_BLOCK
    start_block = ((genesis + 4999) // 5000) * 5000

    blocks = []
    current = start_block
    while current <= latest_block:
        blocks.append(current)
        current += 5000

    return blocks


def update_checkpoints(blocks_to_add: List[int]) -> bool:
    """
    Update the CHECKPOINTS_MAINNET dictionary in check.py with new hash values
    for the specified blocks.
    """
    check_py_path = Path(__file__).resolve().parent.parent / "src" / "index_core" / "check.py"

    try:
        # Read the entire check.py file by lines to handle the file more precisely
        with open(check_py_path, "r") as f:
            lines = f.readlines()

        # Get all blocks and their hashes from the database
        new_entries = {}
        for block in blocks_to_add:
            hashes = get_checkpoint_hashes(block)
            if hashes:
                ledger_hash, txlist_hash = hashes
                new_entries[block] = (ledger_hash, txlist_hash)

        if not new_entries:
            logger.warning("No new entries to add")
            return False

        # Find the CHECKPOINTS_MAINNET dictionary in the file
        start_line = -1
        end_line = -1
        for i, line in enumerate(lines):
            if "CHECKPOINTS_MAINNET" in line and "=" in line:
                start_line = i
                break

        if start_line == -1:
            logger.error("Could not find CHECKPOINTS_MAINNET dictionary declaration")
            return False

        # Find the end of the dictionary
        brace_count = lines[start_line].count("{")
        for i in range(start_line + 1, len(lines)):
            line = lines[i]
            brace_count += line.count("{") - line.count("}")
            if brace_count == 0:
                end_line = i
                break

        if end_line == -1:
            logger.error("Could not find the end of CHECKPOINTS_MAINNET dictionary")
            return False

        # Extract existing blocks
        existing_blocks = set()
        for i in range(start_line, end_line):
            line = lines[i]
            if ":" in line and "{" in line and not line.strip().startswith("#"):
                # Extract block height
                block_str = line.split(":")[0].strip()
                if block_str.isdigit():
                    existing_blocks.add(int(block_str))

        logger.info(f"Found {len(existing_blocks)} existing checkpoint entries")

        # Create entries for new blocks
        new_entries_text = ""
        for block, (ledger_hash, txlist_hash) in sorted(new_entries.items()):
            if block not in existing_blocks:
                new_entries_text += f"""    {block}: {{
        "ledger_hash": "{ledger_hash}",
        "txlist_hash": "{txlist_hash}",
    }},
"""
                logger.info(f"Adding new checkpoint for block {block}")
            else:
                logger.info(f"Block {block} already exists in checkpoints, skipping")

        if not new_entries_text:
            logger.info("No new entries to add (all blocks already exist)")
            return True

        # Insert the new entries right before the closing brace
        closing_brace_line = lines[end_line].rstrip()
        # Make sure we preserve the newline at the end
        if not closing_brace_line.endswith("\n"):
            closing_brace_line += "\n"
        lines[end_line] = new_entries_text + closing_brace_line

        # Ensure there's always a blank line after the dictionary
        if end_line + 1 < len(lines):
            # Check if there's already a blank line
            if lines[end_line].endswith("\n") and not lines[end_line].endswith("\n\n"):
                # Only one newline, add another
                lines[end_line] = lines[end_line].rstrip("\n") + "\n\n"
            elif not lines[end_line].endswith("\n"):
                # No newline, add two
                lines[end_line] = lines[end_line] + "\n\n"

        # Write the updated content back to the file
        with open(check_py_path, "w") as f:
            f.writelines(lines)

        logger.info(f"Successfully updated checkpoints in {check_py_path}")
        return True

    except Exception as e:
        logger.error(f"Error updating checkpoints: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False


def main() -> None:
    """Main function to update checkpoint hashes"""
    latest_block = get_latest_block()
    if latest_block == 0:
        logger.error("Could not determine latest block, exiting")
        return

    logger.info(f"Latest block: {latest_block}")

    # Calculate 5000-block intervals, only include multiples of 5000
    blocks = calculate_5000_blocks(latest_block)

    logger.info(f"Blocks to update: {blocks}")

    # Update checkpoints in check.py
    if update_checkpoints(blocks):
        logger.info("Checkpoint update completed successfully")
    else:
        logger.error("Checkpoint update failed")


if __name__ == "__main__":
    main()
