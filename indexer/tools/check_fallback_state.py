#!/usr/bin/env python3
"""Check and clear fallback state from reprocess_queue.db"""

import sqlite3
import sys
from pathlib import Path

# Database path
db_path = Path(__file__).parent.parent / "reprocess_queue.db"

if not db_path.exists():
    print(f"Database not found at {db_path}")
    sys.exit(1)

# Connect to database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check fallback sessions
    cursor.execute("SELECT * FROM fallback_sessions ORDER BY start_block_index")
    sessions = cursor.fetchall()

    if sessions:
        print(f"Found {len(sessions)} fallback sessions:")
        for session in sessions:
            print(f"  Session ID: {session[0]}, Start Block: {session[1]}, Created: {session[2]}")

            # Check failed blocks for this session
            cursor.execute("SELECT COUNT(*) FROM failed_blocks WHERE session_id = ?", (session[0],))
            block_count = cursor.fetchone()[0]
            print(f"    Failed blocks in session: {block_count}")
    else:
        print("No fallback sessions found in database")

    # Check for any orphaned failed blocks
    cursor.execute("""
        SELECT COUNT(*) FROM failed_blocks 
        WHERE session_id NOT IN (SELECT id FROM fallback_sessions)
    """)
    orphaned = cursor.fetchone()[0]
    if orphaned > 0:
        print(f"\nWARNING: Found {orphaned} orphaned failed block records")

    # Get statistics
    cursor.execute("SELECT MIN(start_block_index), MAX(start_block_index) FROM fallback_sessions")
    min_block, max_block = cursor.fetchone()
    if min_block:
        print(f"\nBlock range: {min_block} to {max_block}")

        if min_block == 12345:
            print("\n⚠️  WARNING: Found test data (block 12345) in production database!")
            print("This is causing the production indexer to rollback incorrectly.")

            response = input("\nDo you want to clear ALL fallback state? (yes/no): ")
            if response.lower() == "yes":
                cursor.execute("DELETE FROM fallback_sessions")
                cursor.execute("DELETE FROM failed_blocks")
                conn.commit()
                print("✅ Cleared all fallback state from database")
            else:
                print("❌ Fallback state not cleared")

finally:
    conn.close()
