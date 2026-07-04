#!/usr/bin/env python3
"""
Rollback and reprocess blocks that were processed in fallback mode.

This script helps identify blocks that were processed without Counterparty data
and provides utilities to rollback and reprocess them with full CP data.
"""

import argparse
import logging
import os
import sys
from typing import List, Optional

from dotenv import load_dotenv

# Load environment variables before any project imports
load_dotenv()

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config
from index_core.database import DatabaseManager
from index_core.pipeline_utils import CPBlocksPipeline

logger = logging.getLogger(__name__)


def find_fallback_blocks(start_block: Optional[int] = None, end_block: Optional[int] = None) -> List[int]:
    """
    Find blocks that were processed in fallback mode.

    These blocks will have missing or incomplete Counterparty data and need reprocessing.

    Args:
        start_block: Optional starting block to search from
        end_block: Optional ending block to search to

    Returns:
        List of block indices that need reprocessing
    """
    db = DatabaseManager()

    # Query for blocks that might be missing CP data
    # We look for blocks that have transactions but no CP issuances
    query = """
    SELECT DISTINCT b.block_index 
    FROM blocks b
    LEFT JOIN StampTableV4 s ON b.block_index = s.block_index
    WHERE b.block_index IS NOT NULL
    AND s.block_index IS NULL
    """

    params = []
    if start_block is not None:
        query += " AND b.block_index >= %s"
        params.append(start_block)
    if end_block is not None:
        query += " AND b.block_index <= %s"
        params.append(end_block)

    query += " ORDER BY b.block_index"

    try:
        with db.get_cursor() as cursor:
            cursor.execute(query, params)
            results = cursor.fetchall()
            return [row[0] for row in results]
    except Exception as e:
        logger.error(f"Error finding fallback blocks: {e}")
        return []


def check_pipeline_fallback_status():
    """
    Check if there's an active pipeline in fallback mode and get its status.
    """
    try:
        # This would need to be implemented to check active pipeline status
        # For now, just return configuration status
        return {
            "fallback_mode_enabled": config.CP_FALLBACK_MODE,
            "message": "Fallback mode is enabled in configuration" if config.CP_FALLBACK_MODE else "Fallback mode is disabled",
        }
    except Exception as e:
        logger.error(f"Error checking pipeline status: {e}")
        return {"error": str(e)}


def suggest_rollback_point(fallback_blocks: List[int]) -> Optional[int]:
    """
    Suggest an optimal rollback point based on fallback blocks found.

    Args:
        fallback_blocks: List of blocks that were processed in fallback mode

    Returns:
        Suggested block to rollback to, or None if no rollback needed
    """
    if not fallback_blocks:
        return None

    # Find the earliest consecutive sequence of fallback blocks
    if len(fallback_blocks) == 1:
        return fallback_blocks[0]

    # Look for gaps to find the best rollback point
    consecutive_start = fallback_blocks[0]
    for i in range(1, len(fallback_blocks)):
        if fallback_blocks[i] - fallback_blocks[i - 1] > 1:
            # Found a gap, suggest rolling back to the start of the sequence
            break

    return consecutive_start


def print_rollback_commands(rollback_block: int):
    """
    Print the commands needed to perform the rollback and reprocessing.

    Args:
        rollback_block: The block to rollback to
    """
    print(f"\n📋 Rollback and Reprocessing Commands:")
    print(f"   1. Rollback database to block {rollback_block}:")
    print(f"      cd indexer && poetry run python tools/rollback_db.py {rollback_block}")
    print(f"   2. Ensure CP fallback mode is disabled:")
    print(f"      export CP_FALLBACK_MODE=false")
    print(f"   3. Restart indexer from block {rollback_block}:")
    print(f"      cd indexer && poetry run indexer --start-block {rollback_block}")
    print(f"\n⚠️  Make sure Counterparty nodes are healthy before reprocessing!")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Manage fallback mode rollbacks and reprocessing.")
    parser.add_argument("--find-blocks", action="store_true", help="Find blocks processed in fallback mode")
    parser.add_argument("--start-block", type=int, help="Starting block to search from")
    parser.add_argument("--end-block", type=int, help="Ending block to search to")
    parser.add_argument("--suggest-rollback", action="store_true", help="Suggest optimal rollback point")
    parser.add_argument("--check-status", action="store_true", help="Check pipeline fallback status")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.check_status:
        print("🔍 Checking pipeline fallback status...")
        status = check_pipeline_fallback_status()
        print(f"   Status: {status}")
        return

    if args.find_blocks:
        print(f"🔍 Searching for blocks processed in fallback mode...")
        if args.start_block:
            print(f"   Starting from block: {args.start_block}")
        if args.end_block:
            print(f"   Ending at block: {args.end_block}")

        fallback_blocks = find_fallback_blocks(args.start_block, args.end_block)

        if not fallback_blocks:
            print("✅ No blocks found that were processed in fallback mode.")
            return

        print(f"📦 Found {len(fallback_blocks)} blocks that may need reprocessing:")

        # Show first 20 blocks
        display_blocks = fallback_blocks[:20]
        print(f"   Blocks: {display_blocks}")
        if len(fallback_blocks) > 20:
            print(f"   ... and {len(fallback_blocks) - 20} more blocks")

        if args.suggest_rollback:
            rollback_point = suggest_rollback_point(fallback_blocks)
            if rollback_point:
                print(f"\n💡 Suggested rollback point: block {rollback_point}")
                print_rollback_commands(rollback_point)
            else:
                print("\n❓ No clear rollback point could be determined.")

    if not any([args.find_blocks, args.check_status]):
        parser.print_help()


if __name__ == "__main__":
    main()
