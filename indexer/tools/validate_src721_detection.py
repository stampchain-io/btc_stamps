#!/usr/bin/env python3
"""
Validate that SRC-721 detection from description field is working correctly.
Compare stamps between production and development databases.
"""

import os
import sys

import pymysql
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configurations
PROD_CONFIG = {
    "host": os.environ.get("ST3_HOSTNAME"),
    "user": os.environ.get("ST3_USER"),
    "password": os.environ.get("ST3_PASSWORD"),
    "database": os.environ.get("PROD_DATABASE"),
    "port": int(os.environ.get("ST3_PORT", 3306)),
}

DEV_CONFIG = {
    "host": os.environ.get("RDS_HOSTNAME"),
    "user": os.environ.get("RDS_USER"),
    "password": os.environ.get("RDS_PASSWORD"),
    "database": "btc_stamps",
    "port": int(os.environ.get("RDS_PORT", 3306)),
}


def connect_db(config, name):
    """Connect to database."""
    try:
        conn = pymysql.connect(**config)
        print(f"✅ Connected to {name} database")
        return conn
    except Exception as e:
        print(f"❌ Failed to connect to {name} database: {e}")
        return None


def get_stamp_721_patterns(conn, db_name):
    """Get stamps with stamp:721 pattern in description."""
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # Different table names in prod vs dev
    stamp_table = "stamp_table" if db_name == "Production" else "stamps"

    query = f"""
    SELECT 
        s.tx_hash,
        s.stamp,
        s.cpid,
        s.ident,
        s.block_index,
        s.is_btc_stamp,
        s.is_cursed,
        s.stamp_mimetype,
        s.file_suffix
    FROM {stamp_table} s
    WHERE s.cpid IN (
        SELECT asset_name 
        FROM assets 
        WHERE LOWER(description) LIKE 'stamp:721%'
    )
    ORDER BY s.block_index DESC
    LIMIT 100
    """

    try:
        cursor.execute(query)
        results = cursor.fetchall()
        return results
    except Exception as e:
        print(f"Error querying {db_name}: {e}")
        return []
    finally:
        cursor.close()


def validate_results(prod_results, dev_results):
    """Compare results between production and development."""
    print("\n" + "=" * 100)
    print("VALIDATION RESULTS")
    print("=" * 100)

    # Create lookup by tx_hash
    prod_by_tx = {r["tx_hash"]: r for r in prod_results}
    dev_by_tx = {r["tx_hash"]: r for r in dev_results}

    # Track statistics
    total_checked = 0
    correctly_changed = 0
    incorrectly_unchanged = 0
    other_issues = 0

    # Check each transaction
    all_tx_hashes = set(prod_by_tx.keys()) | set(dev_by_tx.keys())

    for tx_hash in sorted(all_tx_hashes):
        prod_data = prod_by_tx.get(tx_hash)
        dev_data = dev_by_tx.get(tx_hash)

        if not prod_data or not dev_data:
            print(f"\n⚠️  TX {tx_hash} missing in {'production' if not prod_data else 'development'}")
            other_issues += 1
            continue

        total_checked += 1

        # Check if ident changed from STAMP to SRC-721
        if prod_data["ident"] == "STAMP" and dev_data["ident"] == "SRC-721":
            correctly_changed += 1
            print(f"\n✅ TX {tx_hash}: STAMP → SRC-721 (correct)")
            print(f"   Block: {dev_data['block_index']}")
            print(f"   CPID: {dev_data['cpid']}")

        elif prod_data["ident"] == "STAMP" and dev_data["ident"] == "STAMP":
            incorrectly_unchanged += 1
            print(f"\n❌ TX {tx_hash}: STAMP → STAMP (should be SRC-721)")
            print(f"   Block: {dev_data['block_index']}")
            print(f"   CPID: {dev_data['cpid']}")

        elif prod_data["ident"] == dev_data["ident"]:
            # No change expected (already correct or other protocol)
            if dev_data["ident"] == "SRC-721":
                print(f"\n✅ TX {tx_hash}: Already SRC-721 in both")
            else:
                print(f"\n🔍 TX {tx_hash}: {prod_data['ident']} → {dev_data['ident']} (no change)")

        else:
            other_issues += 1
            print(f"\n⚠️  TX {tx_hash}: {prod_data['ident']} → {dev_data['ident']} (unexpected change)")

        # Check other fields remain the same
        if prod_data["stamp"] != dev_data["stamp"]:
            print(f"   ⚠️  Stamp number changed: {prod_data['stamp']} → {dev_data['stamp']}")
        if prod_data["is_cursed"] != dev_data["is_cursed"]:
            print(f"   ⚠️  Cursed status changed: {prod_data['is_cursed']} → {dev_data['is_cursed']}")

    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Total stamps with stamp:721 pattern checked: {total_checked}")
    print(f"✅ Correctly changed from STAMP to SRC-721: {correctly_changed}")
    print(f"❌ Incorrectly remained as STAMP: {incorrectly_unchanged}")
    print(f"⚠️  Other issues: {other_issues}")

    if incorrectly_unchanged == 0 and other_issues == 0:
        print("\n🎉 All stamps with stamp:721 pattern are correctly identified as SRC-721!")
        return True
    else:
        print("\n⚠️  Some issues found - please investigate")
        return False


def check_cursed_stamps(prod_conn, dev_conn):
    """Verify cursed stamp counts match."""
    print("\n" + "=" * 100)
    print("CURSED STAMP VALIDATION")
    print("=" * 100)

    for conn, name, table in [(prod_conn, "Production", "stamp_table"), (dev_conn, "Development", "stamps")]:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE stamp < 0")
        count = cursor.fetchone()[0]
        cursor.close()
        print(f"{name} cursed stamps: {count}")


def main():
    """Main validation function."""
    print("SRC-721 Description Field Detection Validation")
    print("=" * 100)

    # Connect to databases
    prod_conn = connect_db(PROD_CONFIG, "Production")
    dev_conn = connect_db(DEV_CONFIG, "Development")

    if not prod_conn or not dev_conn:
        print("\nCannot proceed without database connections")
        return 1

    try:
        # Get stamps with stamp:721 pattern
        print("\nFetching stamps with stamp:721 pattern...")
        prod_results = get_stamp_721_patterns(prod_conn, "Production")
        dev_results = get_stamp_721_patterns(dev_conn, "Development")

        print(f"Found {len(prod_results)} in production, {len(dev_results)} in development")

        # Validate the results
        success = validate_results(prod_results, dev_results)

        # Also check cursed stamps haven't changed
        check_cursed_stamps(prod_conn, dev_conn)

        return 0 if success else 1

    finally:
        prod_conn.close()
        dev_conn.close()


if __name__ == "__main__":
    sys.exit(main())
