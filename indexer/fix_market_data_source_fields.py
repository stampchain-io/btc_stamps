#!/usr/bin/env python3
"""
Fix script to update NULL price_source fields in production database
"""
import os
import sys

import pymysql
from dotenv import load_dotenv

# Load environment variables
if os.getcwd().endswith("/indexer"):
    dotenv_path = os.path.join(os.getcwd(), ".env")
else:
    dotenv_path = os.path.join(os.getcwd(), "indexer/.env")

load_dotenv(dotenv_path=dotenv_path, override=True)

# Production database connection
prod_host = os.environ.get("ST3_HOSTNAME")
prod_user = os.environ.get("ST3_USER")
prod_password = os.environ.get("ST3_PASSWORD")
prod_database = os.environ.get("PROD_DATABASE", "btc_stamps")

print(f"Connecting to production database: {prod_host}/{prod_database}")

conn = pymysql.connect(host=prod_host, user=prod_user, password=prod_password, database=prod_database)

cursor = conn.cursor()

try:
    # First, check current state
    print("\n=== Current State Analysis ===")

    cursor.execute(
        """
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN price_source IS NULL THEN 1 END) as null_price_source,
            COUNT(CASE WHEN price_source = 'counterparty' THEN 1 END) as counterparty_source,
            COUNT(CASE WHEN price_source = 'dispenser' THEN 1 END) as dispenser_source,
            COUNT(CASE WHEN volume_sources IS NULL OR volume_sources = '{}' THEN 1 END) as empty_volume_sources
        FROM stamp_market_data
    """
    )

    result = cursor.fetchone()
    print(f"Total stamps: {result[0]}")
    print(f"NULL price_source: {result[1]}")
    print(f"'counterparty' price_source: {result[2]}")
    print(f"'dispenser' price_source: {result[3]}")
    print(f"Empty volume_sources: {result[4]}")

    # Fix 1: Update NULL price_source to 'counterparty' as default
    print("\n=== Fixing NULL price_source fields ===")

    cursor.execute(
        """
        UPDATE stamp_market_data
        SET price_source = 'counterparty'
        WHERE price_source IS NULL
    """
    )

    fixed_count = cursor.rowcount
    print(f"Updated {fixed_count} records with price_source = 'counterparty'")

    # Fix 2: For stamps with dispensers, set price_source to 'dispenser'
    print("\n=== Setting price_source = 'dispenser' for stamps with active dispensers ===")

    cursor.execute(
        """
        UPDATE stamp_market_data
        SET price_source = 'dispenser'
        WHERE open_dispensers_count > 0
        AND floor_price_btc IS NOT NULL
    """
    )

    dispenser_count = cursor.rowcount
    print(f"Updated {dispenser_count} records with price_source = 'dispenser'")

    # Fix 3: Set volume_sources for stamps with volume data
    print("\n=== Setting volume_sources for stamps with volume ===")

    cursor.execute(
        """
        UPDATE stamp_market_data
        SET volume_sources = 'dispenser'
        WHERE (volume_24h_btc > 0 OR volume_7d_btc > 0 OR volume_30d_btc > 0)
        AND (volume_sources IS NULL OR volume_sources = '{}')
    """
    )

    volume_count = cursor.rowcount
    print(f"Updated {volume_count} records with volume_sources = 'dispenser'")

    # Commit changes
    conn.commit()
    print("\n✓ All changes committed successfully")

    # Verify results
    print("\n=== Verification ===")

    cursor.execute(
        """
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN price_source IS NULL THEN 1 END) as null_price_source,
            COUNT(CASE WHEN price_source = 'counterparty' THEN 1 END) as counterparty_source,
            COUNT(CASE WHEN price_source = 'dispenser' THEN 1 END) as dispenser_source,
            COUNT(CASE WHEN volume_sources IS NULL OR volume_sources = '{}' THEN 1 END) as empty_volume_sources,
            COUNT(CASE WHEN volume_sources = 'dispenser' THEN 1 END) as dispenser_volume
        FROM stamp_market_data
    """
    )

    result = cursor.fetchone()
    print(f"Total stamps: {result[0]}")
    print(f"NULL price_source: {result[1]} (should be 0)")
    print(f"'counterparty' price_source: {result[2]}")
    print(f"'dispenser' price_source: {result[3]}")
    print(f"Empty volume_sources: {result[4]}")
    print(f"'dispenser' volume_sources: {result[5]}")

    # Check some specific high-value stamps
    print("\n=== Sample High-Value Stamps ===")

    cursor.execute(
        """
        SELECT cpid, price_source, volume_sources, floor_price_btc, 
               volume_24h_btc, open_dispensers_count
        FROM stamp_market_data
        WHERE floor_price_btc IS NOT NULL
        ORDER BY floor_price_btc DESC
        LIMIT 5
    """
    )

    for row in cursor.fetchall():
        print(f"\nCPID: {row[0]}")
        print(f"  price_source: {row[1]}")
        print(f"  volume_sources: {row[2]}")
        print(f"  floor_price_btc: {row[3]}")
        print(f"  volume_24h_btc: {row[4]}")
        print(f"  open_dispensers: {row[5]}")

finally:
    cursor.close()
    conn.close()
