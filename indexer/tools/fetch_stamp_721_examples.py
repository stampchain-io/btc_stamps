#!/usr/bin/env python3
"""
Fetch examples of stamps with stamp:721 pattern in description from production database.
This helps validate our implementation against real data.
"""

import json
import os
import sys

import pymysql
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load environment variables
load_dotenv()

# Production database configuration (ST3)
PROD_CONFIG = {
    "host": os.environ.get("ST3_HOSTNAME"),
    "user": os.environ.get("ST3_USER"),
    "password": os.environ.get("ST3_PASSWORD"),
    "database": os.environ.get("PROD_DATABASE"),
    "port": int(os.environ.get("ST3_PORT", 3306)),
}


def connect_to_production():
    """Connect to production database."""
    try:
        conn = pymysql.connect(**PROD_CONFIG)
        print("✅ Connected to production database")
        return conn
    except Exception as e:
        print(f"❌ Failed to connect to production database: {e}")
        return None


def fetch_stamp_721_examples(conn, limit=10):
    """Fetch examples of stamps with stamp:721 pattern in description."""
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # Query to find stamps with stamp:721 pattern
    # Note: Production may not have these marked as SRC-721 yet
    query = """
    SELECT 
        s.tx_hash,
        s.stamp,
        s.cpid,
        s.ident,
        s.block_index,
        s.is_btc_stamp,
        s.is_cursed,
        s.stamp_mimetype,
        s.file_suffix,
        a.description,
        t.p2wsh_data IS NOT NULL as has_p2wsh
    FROM stamps s
    JOIN issuances i ON s.cpid = i.asset
    JOIN assets a ON i.asset = a.asset_name
    LEFT JOIN transactions t ON s.tx_hash = t.tx_hash
    WHERE LOWER(a.description) LIKE 'stamp:721%'
    ORDER BY s.block_index DESC
    LIMIT %s
    """

    try:
        cursor.execute(query, (limit,))
        results = cursor.fetchall()

        print(f"\nFound {len(results)} stamps with stamp:721 pattern in description:")
        print("=" * 120)

        for i, row in enumerate(results, 1):
            print(f"\n{i}. Transaction: {row['tx_hash']}")
            print(f"   Block: {row['block_index']}")
            print(f"   Stamp: {row['stamp']}")
            print(f"   CPID: {row['cpid']}")
            print(f"   Current Ident: {row['ident']} {'⚠️  Should be SRC-721' if row['ident'] != 'SRC-721' else '✅'}")
            print(f"   Is BTC Stamp: {row['is_btc_stamp']}")
            print(f"   Is Cursed: {row['is_cursed']}")
            print(f"   MIME Type: {row['stamp_mimetype']}")
            print(f"   File Suffix: {row['file_suffix']}")
            print(f"   Has P2WSH: {row['has_p2wsh']}")
            print(
                f"   Description: {row['description'][:100]}..."
                if len(row["description"]) > 100
                else f"   Description: {row['description']}"
            )

        return results

    except Exception as e:
        print(f"Error fetching data: {e}")
        return []
    finally:
        cursor.close()


def fetch_p2wsh_stamps(conn, limit=5):
    """Fetch recent P2WSH stamps to check if any have stamp:721 pattern."""
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    query = """
    SELECT 
        s.tx_hash,
        s.stamp,
        s.cpid,
        s.ident,
        s.block_index,
        s.stamp_mimetype,
        a.description
    FROM stamps s
    JOIN transactions t ON s.tx_hash = t.tx_hash
    LEFT JOIN issuances i ON s.cpid = i.asset
    LEFT JOIN assets a ON i.asset = a.asset_name
    WHERE t.p2wsh_data IS NOT NULL
    AND s.block_index > 850000
    ORDER BY s.block_index DESC
    LIMIT %s
    """

    try:
        cursor.execute(query, (limit,))
        results = cursor.fetchall()

        print(f"\n\nRecent P2WSH stamps:")
        print("=" * 120)

        for row in results:
            has_stamp_721 = (
                row["description"] and row["description"].lower().startswith("stamp:721") if row["description"] else False
            )

            print(f"\nTransaction: {row['tx_hash']}")
            print(f"   Block: {row['block_index']}")
            print(f"   CPID: {row['cpid']}")
            print(f"   Ident: {row['ident']}")
            print(f"   MIME Type: {row['stamp_mimetype']}")
            print(f"   Description: {row['description'][:100] if row['description'] else 'None'}")
            if has_stamp_721:
                print(f"   🎯 HAS stamp:721 pattern - should be SRC-721!")

    except Exception as e:
        print(f"Error fetching P2WSH data: {e}")
    finally:
        cursor.close()


def main():
    """Main function."""
    conn = connect_to_production()
    if not conn:
        return

    try:
        # Fetch stamps with stamp:721 pattern
        stamp_721_examples = fetch_stamp_721_examples(conn, limit=20)

        # Also check recent P2WSH stamps
        fetch_p2wsh_stamps(conn, limit=10)

        # Summary
        if stamp_721_examples:
            non_src721 = [s for s in stamp_721_examples if s["ident"] != "SRC-721"]
            if non_src721:
                print(f"\n\n⚠️  Found {len(non_src721)} stamps with stamp:721 pattern not marked as SRC-721")
                print("These should become SRC-721 with the new implementation.")
            else:
                print("\n\n✅ All stamps with stamp:721 pattern are already marked as SRC-721")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
