#!/usr/bin/env python3
"""
Clear database back to a specific block index.
"""

import argparse
import os
import sys

import pymysql
from dotenv import load_dotenv

# Load environment variables BEFORE any project imports
load_dotenv()

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from index_core.database import perform_complete_rollback
from index_core.fallback_state import get_fallback_state_manager


def clear_database(block_index, db_host=None, db_user=None, db_password=None, db_name=None):
    """
    Clear database back to a specific block index.
    """
    # Load environment variables if not provided
    if not all([db_host, db_user, db_password, db_name]):
        load_dotenv()
        db_host = db_host or os.environ.get("RDS_HOSTNAME")
        db_user = db_user or os.environ.get("RDS_USER")
        db_password = db_password or os.environ.get("RDS_PASSWORD")
        db_name = db_name or os.environ.get("RDS_DATABASE", "btc_stamps")

    print(f"Connecting to database {db_name} on {db_host} as {db_user}")

    # Connect to the database
    try:
        conn = pymysql.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
        )
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

    print(f"Connected to database. Clearing data from block {block_index} onwards...")

    # Create a cursor
    cursor = conn.cursor()

    try:
        # Disable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")

        # Core tables
        print("Clearing transactions table...")
        cursor.execute(f"DELETE FROM transactions WHERE block_index >= {block_index};")  # nosec B608
        print(f"Deleted {cursor.rowcount} rows from transactions")

        print("Clearing blocks table...")
        cursor.execute(f"DELETE FROM blocks WHERE block_index >= {block_index};")  # nosec B608
        print(f"Deleted {cursor.rowcount} rows from blocks")

        # Stamp related
        print("Clearing StampTableV4 table...")
        cursor.execute(f"DELETE FROM StampTableV4 WHERE block_index >= {block_index};")  # nosec B608
        print(f"Deleted {cursor.rowcount} rows from StampTableV4")

        # SRC20 related
        print("Clearing SRC20 table...")
        cursor.execute(f"DELETE FROM SRC20 WHERE block_index >= {block_index};")  # nosec B608
        print(f"Deleted {cursor.rowcount} rows from SRC20")

        print("Clearing SRC20Valid table...")
        cursor.execute(f"DELETE FROM SRC20Valid WHERE block_index >= {block_index};")  # nosec B608
        print(f"Deleted {cursor.rowcount} rows from SRC20Valid")

        print("Clearing balances table...")
        cursor.execute("DELETE FROM balances;")
        print(f"Deleted {cursor.rowcount} rows from balances")

        # SRC101 related
        print("Clearing SRC101 table...")
        cursor.execute(f"DELETE FROM SRC101 WHERE block_index >= {block_index};")  # nosec B608
        print(f"Deleted {cursor.rowcount} rows from SRC101")

        print("Clearing SRC101Valid table...")
        cursor.execute(f"DELETE FROM SRC101Valid WHERE block_index >= {block_index};")  # nosec B608
        print(f"Deleted {cursor.rowcount} rows from SRC101Valid")

        print("Clearing src101price table...")
        cursor.execute(f"DELETE FROM src101price WHERE block_index >= {block_index};")  # nosec B608
        print(f"Deleted {cursor.rowcount} rows from src101price")

        print("Clearing recipients table...")
        cursor.execute(f"DELETE FROM recipients WHERE block_index >= {block_index};")  # nosec B608
        print(f"Deleted {cursor.rowcount} rows from recipients")

        print("Clearing owners table...")
        cursor.execute("DELETE FROM owners;")
        print(f"Deleted {cursor.rowcount} rows from owners")

        # Re-enable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

        # Commit the changes
        conn.commit()
        print("Database cleared successfully!")

        # Check if we should clear fallback state
        fallback_manager = get_fallback_state_manager()
        if fallback_manager.is_fallback_active():
            fallback_start_block = fallback_manager.get_fallback_start_block()
            if fallback_start_block and block_index <= fallback_start_block:
                print(f"\nClearing fallback state (started at block {fallback_start_block})...")
                fallback_manager.end_fallback_mode()
                print("Fallback state cleared successfully!")
            else:
                print(f"\nNote: Fallback mode is active (started at block {fallback_start_block})")
                print(f"To clear fallback state, rollback to block {fallback_start_block} or earlier")

    except Exception as e:
        conn.rollback()
        print(f"Error clearing database: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


def main():
    """
    Main function.
    """
    parser = argparse.ArgumentParser(description="Clear database back to a specific block index.")
    parser.add_argument("block_index", type=int, help="Block index to clear from")
    parser.add_argument("--host", help="Database host")
    parser.add_argument("--user", help="Database user")
    parser.add_argument("--password", help="Database password")
    parser.add_argument("--database", help="Database name")
    parser.add_argument(
        "--use-indexer-method", action="store_true", help="Use the same rollback method as the indexer (recommended)"
    )

    args = parser.parse_args()

    if args.use_indexer_method or not any([args.host, args.user, args.password]):
        # Use the indexer's rollback method (recommended)
        perform_complete_rollback(args.block_index)
    else:
        # Use the legacy direct SQL method
        clear_database(args.block_index, args.host, args.user, args.password, args.database)


if __name__ == "__main__":
    main()
