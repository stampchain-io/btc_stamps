#!/usr/bin/env python3
"""
Validate and clean up reprocess queue state to ensure production safety.

This script:
1. Checks for any test data in the reprocess queue
2. Validates all fallback sessions
3. Optionally cleans up invalid data
"""

import os
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.index_core.reprocess_safety import (
    ReprocessSafetyError,
    get_safe_reprocess_db_path,
    is_production_environment,
    validate_block_number,
    validate_fallback_state,
)


def check_database(db_path: str, auto_clean: bool = False) -> bool:
    """
    Check database for invalid data.

    Returns True if database is clean, False if issues found.
    """
    if not os.path.exists(db_path):
        print(f"✅ Database not found at {db_path} - no issues")
        return True

    print(f"\nChecking database: {db_path}")
    print(f"Production environment: {is_production_environment()}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    issues_found = False

    try:
        # Check fallback sessions (limit to 1000 for memory efficiency)
        cursor.execute("SELECT id, start_block_index, created_at FROM fallback_sessions ORDER BY start_block_index LIMIT 1000")
        sessions = cursor.fetchall()

        if sessions:
            print(f"\nFound {len(sessions)} fallback sessions:")
            invalid_sessions = []

            for session_id, start_block, created_at in sessions:
                try:
                    validate_block_number(start_block, "session start")

                    # Get failed blocks for this session
                    cursor.execute("SELECT COUNT(*) FROM failed_blocks WHERE session_id = ?", (session_id,))
                    block_count = cursor.fetchone()[0]

                    print(f"  ✅ Session {session_id}: block {start_block}, {block_count} failed blocks, created {created_at}")

                except ReprocessSafetyError as e:
                    print(f"  ❌ Session {session_id}: block {start_block} - INVALID: {e}")
                    invalid_sessions.append(session_id)
                    issues_found = True

            if invalid_sessions and auto_clean:
                print(f"\n🧹 Cleaning {len(invalid_sessions)} invalid sessions...")
                for session_id in invalid_sessions:
                    cursor.execute("DELETE FROM fallback_sessions WHERE id = ?", (session_id,))
                    cursor.execute("DELETE FROM failed_blocks WHERE session_id = ?", (session_id,))
                conn.commit()
                print("✅ Invalid sessions cleaned")
            elif invalid_sessions:
                print(f"\n⚠️  Found {len(invalid_sessions)} invalid sessions. Run with --clean to remove them.")
        else:
            print("\n✅ No fallback sessions found")

        # Check for orphaned failed blocks
        cursor.execute("""
            SELECT COUNT(*) FROM failed_blocks 
            WHERE session_id NOT IN (SELECT id FROM fallback_sessions)
        """)
        orphaned_count = cursor.fetchone()[0]

        if orphaned_count > 0:
            print(f"\n⚠️  Found {orphaned_count} orphaned failed blocks")
            issues_found = True

            if auto_clean:
                cursor.execute("""
                    DELETE FROM failed_blocks 
                    WHERE session_id NOT IN (SELECT id FROM fallback_sessions)
                """)
                conn.commit()
                print("✅ Orphaned blocks cleaned")

        # Check reprocess queue for old entries
        cursor.execute("""
            SELECT COUNT(*) FROM reprocess_queue 
            WHERE added_at < CAST(strftime('%s', 'now') AS INTEGER) - 86400
        """)
        old_entries = cursor.fetchone()[0]

        if old_entries > 0:
            print(f"\n⚠️  Found {old_entries} reprocess queue entries older than 24 hours")

            if auto_clean:
                cursor.execute("""
                    DELETE FROM reprocess_queue 
                    WHERE added_at < CAST(strftime('%s', 'now') AS INTEGER) - 86400
                """)
                conn.commit()
                print("✅ Old queue entries cleaned")

        return not issues_found

    finally:
        conn.close()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate reprocess queue state")
    parser.add_argument("--clean", action="store_true", help="Automatically clean invalid data")
    parser.add_argument("--db-path", help="Override database path")
    args = parser.parse_args()

    # Get database path
    if args.db_path:
        db_path = args.db_path
    else:
        db_path = get_safe_reprocess_db_path()

    print("=" * 60)
    print("Reprocess Queue State Validator")
    print("=" * 60)

    # Check the database
    is_clean = check_database(db_path, auto_clean=args.clean)

    print("\n" + "=" * 60)
    if is_clean:
        print("✅ Database is clean - no issues found")
    else:
        print("❌ Issues found in database")
        if not args.clean:
            print("   Run with --clean to fix automatically")

    # Also check for the bad database file
    bad_db_path = "reprocess_queue.db.bad"
    if os.path.exists(bad_db_path):
        print(f"\n⚠️  Found bad database backup at {bad_db_path}")
        print("   This file contains the problematic test data and should be deleted")

    return 0 if is_clean else 1


if __name__ == "__main__":
    sys.exit(main())
