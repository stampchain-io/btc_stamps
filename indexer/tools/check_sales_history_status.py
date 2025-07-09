#!/usr/bin/env python3
"""
Check the status of the sales history table to verify it's populating correctly.
"""

import os
import sys
from datetime import datetime, timedelta

import pymysql as mysql
from dotenv import load_dotenv


def check_sales_history_status():
    """Check the current status of the sales history table."""
    # Get RDS connection parameters from environment
    rds_host = os.getenv("RDS_HOSTNAME")
    rds_user = os.getenv("RDS_USER")
    rds_password = os.getenv("RDS_PASSWORD")

    if not all([rds_host, rds_user, rds_password]):
        print("❌ Missing RDS environment variables")
        return

    # Connect to database
    try:
        db = mysql.connect(
            host=rds_host,
            user=rds_user,
            password=rds_password,
            database="btc_stamps",
            charset="utf8mb4",
            cursorclass=mysql.cursors.DictCursor,
            connect_timeout=10,
        )
        cursor = db.cursor()
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return

    print("\n" + "=" * 60)
    print("  SALES HISTORY TABLE STATUS CHECK")
    print("=" * 60)

    try:
        # Get total count
        cursor.execute("SELECT COUNT(*) as count FROM stamp_sales_history")
        result = cursor.fetchone()
        total_count = result["count"] if result else 0
        print(f"\n📊 Total records: {total_count:,}")

        # Get recent records count (last 24 hours)
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM stamp_sales_history 
            WHERE processed_at >= NOW() - INTERVAL 24 HOUR
        """
        )
        result = cursor.fetchone()
        recent_count = result["count"] if result else 0
        print(f"📈 Records in last 24h: {recent_count:,}")

        # Get latest record
        cursor.execute(
            """
            SELECT tx_hash, cpid, block_index, processed_at, block_time 
            FROM stamp_sales_history 
            ORDER BY processed_at DESC 
            LIMIT 1
        """
        )
        latest = cursor.fetchone()
        if latest:
            print(f"\n🔄 Latest record:")
            print(f"   TX: {latest['tx_hash'][:16]}...")
            print(f"   CPID: {latest['cpid']}")
            print(f"   Block: {latest['block_index']:,}")
            print(f"   Processed: {latest['processed_at']}")

        # Get distribution by type
        cursor.execute(
            """
            SELECT 
                COUNT(CASE WHEN cpid LIKE 'A%' THEN 1 END) as cp_stamps,
                COUNT(CASE WHEN cpid NOT LIKE 'A%' THEN 1 END) as regular_stamps
            FROM stamp_sales_history
        """
        )
        dist = cursor.fetchone()
        if dist:
            print(f"\n📊 Distribution:")
            print(f"   CP Stamps (A...): {dist['cp_stamps']:,}")
            print(f"   Regular Stamps: {dist['regular_stamps']:,}")

        # Check for gaps
        cursor.execute(
            """
            SELECT MIN(block_index) as min_block, MAX(block_index) as max_block
            FROM stamp_sales_history
        """
        )
        result = cursor.fetchone()
        if result and result["min_block"] and result["max_block"]:
            print(f"\n📏 Block range: {result['min_block']:,} - {result['max_block']:,}")

            # Check processing rate
            cursor.execute(
                """
                SELECT 
                    DATE(processed_at) as date,
                    COUNT(*) as count
                FROM stamp_sales_history
                WHERE processed_at >= NOW() - INTERVAL 7 DAY
                GROUP BY DATE(processed_at)
                ORDER BY date DESC
            """
            )
            print(f"\n📅 Processing rate (last 7 days):")
            for row in cursor.fetchall():
                print(f"   {row['date']}: {row['count']:,} records")

        # Check if actively processing
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM stamp_sales_history 
            WHERE processed_at >= NOW() - INTERVAL 1 HOUR
        """
        )
        result = cursor.fetchone()
        last_hour = result["count"] if result else 0

        if last_hour > 0:
            print(f"\n✅ Status: ACTIVE (processed {last_hour} records in last hour)")
        else:
            print("\n⚠️  Status: INACTIVE (no records processed in last hour)")

    except Exception as e:
        print(f"\n❌ Error checking sales history: {e}")
    finally:
        cursor.close()
        db.close()

    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    # Load environment variables
    # Add proper path handling
    if os.getcwd().endswith("/indexer"):
        dotenv_path = os.path.join(os.getcwd(), ".env")
    else:
        dotenv_path = os.path.join(os.getcwd(), "indexer/.env")

    load_dotenv(dotenv_path)

    check_sales_history_status()
