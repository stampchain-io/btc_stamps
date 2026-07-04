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
from index_core.reprocess_safety import (
    ReprocessSafetyError,
    validate_block_number,
    validate_rollback_distance,
)
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
    parser.add_argument("--force", action="store_true", help="Override safety checks (DANGEROUS - use only when necessary)")

    args = parser.parse_args()

    # Safety validation BEFORE any prompts
    if not args.force:
        try:
            # Validate the target block
            validate_block_number(args.block_index, "rollback target")

            # Get current block height from database for distance validation
            from index_core.database_manager import DatabaseManager

            db_manager = DatabaseManager()
            db = db_manager.connect()
            cursor = db.cursor()
            cursor.execute("SELECT MAX(block_index) FROM blocks")
            result = cursor.fetchone()
            db.close()

            if result and result[0] is not None:
                current_block = result[0]
            else:
                # If no blocks in database, treat as block 0
                current_block = 0

            # Validate rollback distance
            validate_rollback_distance(current_block, args.block_index)

            print(
                f"✅ Safety checks passed: rollback from {current_block} to {args.block_index} ({current_block - args.block_index} blocks)"
            )
            print()

        except ReprocessSafetyError as e:
            print(f"❌ SAFETY VIOLATION: {e}")
            print()
            print("This rollback appears unsafe and has been blocked.")
            print("To override this safety check, use: poetry run rollback {args.block_index} --force")
            print("WARNING: Only use --force if you are absolutely certain!")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error during safety check: {e}")
            sys.exit(1)
    else:
        # Force flag used - show strong warning
        print("⚠️  WARNING: Safety checks bypassed with --force flag!")
        print("⚠️  This rollback may be dangerous!")
        print()

        # Still get current block for display
        try:
            from index_core.database_manager import DatabaseManager

            db_manager = DatabaseManager()
            db = db_manager.connect()
            cursor = db.cursor()
            cursor.execute("SELECT MAX(block_index) FROM blocks")
            result = cursor.fetchone()
            db.close()

            if result and result[0] is not None:
                current_block = result[0]
                print(f"Rollback from {current_block} to {args.block_index} ({current_block - args.block_index} blocks)")
                print()
        except Exception:
            pass

    # Safety confirmation unless --confirm is used
    if not args.confirm:
        # Show which database will be affected
        db_host = os.environ.get("RDS_HOSTNAME", "localhost")
        db_name = os.environ.get("RDS_DATABASE", "btc_stamps")
        db_port = os.environ.get("RDS_PORT", "3306")
        print(f"📊 Target Database: {db_host}:{db_port}/{db_name}")
        print()
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
        perform_complete_rollback(args.block_index, force=args.force)

        print("✅ Rollback completed successfully!")
        print()
        print("The following operations were performed:")
        print("  ✓ Database tables cleared and rebuilt")
        print("  ✓ Backend cache invalidated")
        print("  ✓ Balances and ownership recalculated")
        print("  ✓ SRC20 token statistics updated")
        print("  ✓ Fallback state cleared (if applicable)")

    except ReprocessSafetyError as e:
        print(f"❌ Safety violation during rollback: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error during rollback: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
