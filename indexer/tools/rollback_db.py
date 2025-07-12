#!/usr/bin/env python3
"""
Clear database back to a specific block index using the indexer's rollback method.

This tool uses the same rollback functionality as the main indexer application,
ensuring consistent behavior and comprehensive cleanup.
"""

import argparse
import os
import sys

from dotenv import load_dotenv

# Load environment variables BEFORE any project imports
load_dotenv()

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from index_core.database import perform_complete_rollback
from index_core.reprocessing_queue import ReprocessingQueue


def main() -> None:
    """
    Main function - performs database rollback using the indexer's method.
    """
    parser = argparse.ArgumentParser(
        description="Clear database back to a specific block index using the indexer's rollback method."
    )
    parser.add_argument("block_index", type=int, help="Block index to clear from")
    parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt (use with caution)")

    args = parser.parse_args()

    # Safety confirmation unless --confirm is used
    if not args.confirm:
        print(f"⚠️  WARNING: This will delete all data from block {args.block_index} onwards!")
        print("This includes:")
        print("  - All transactions and blocks")
        print("  - All Stamps, SRC20, and SRC101 data")
        print("  - All balances and ownership records")
        print("  - All market data and cached information")
        print()

        # Check for fallback state
        try:
            queue = ReprocessingQueue.get_instance()
            oldest_failed_block = queue.get_oldest_failed_block()
            if oldest_failed_block:
                if args.block_index <= oldest_failed_block:
                    print(f"✅ This will also clear fallback state (started at block {oldest_failed_block})")
                else:
                    print(f"ℹ️  Note: Fallback mode is active (started at block {oldest_failed_block})")
                    print(f"   To clear fallback state, rollback to block {oldest_failed_block} or earlier")
                print()
        except Exception:
            # Ignore fallback state check errors
            pass

        response = input("Are you sure you want to proceed? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("Rollback cancelled.")
            sys.exit(0)

    print(f"🔄 Performing rollback to block {args.block_index} using indexer method...")
    print("This uses the same rollback functionality as the main indexer application.")
    print()

    try:
        # Use the indexer's rollback method - same as production
        perform_complete_rollback(args.block_index)

        print("✅ Rollback completed successfully!")
        print()
        print("The following operations were performed:")
        print("  ✓ Database tables cleared and rebuilt")
        print("  ✓ Backend cache invalidated")
        print("  ✓ Balances and ownership recalculated")
        print("  ✓ SRC20 token statistics updated")
        print("  ✓ Fallback state cleared (if applicable)")

    except Exception as e:
        print(f"❌ Error during rollback: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
