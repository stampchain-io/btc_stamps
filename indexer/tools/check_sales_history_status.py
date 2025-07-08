#!/usr/bin/env python3
"""
Check the status of the sales history table to verify it's populating correctly.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add the indexer src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
from index_core.database import DatabaseConnection


def check_sales_history_status():
    """Check the current status of the sales history table."""
    db = DatabaseConnection()
    cursor = db.cursor()
    
    print("\n" + "="*60)
    print("  SALES HISTORY TABLE STATUS CHECK")
    print("="*60)
    
    try:
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM sales_history")
        total_count = cursor.fetchone()[0]
        print(f"\n📊 Total records: {total_count:,}")
        
        # Get recent records count (last 24 hours)
        cursor.execute("""
            SELECT COUNT(*) 
            FROM sales_history 
            WHERE created_at >= NOW() - INTERVAL 24 HOUR
        """)
        recent_count = cursor.fetchone()[0]
        print(f"📈 Records in last 24h: {recent_count:,}")
        
        # Get latest record
        cursor.execute("""
            SELECT tx_hash, cpid, block_index, created_at 
            FROM sales_history 
            ORDER BY created_at DESC 
            LIMIT 1
        """)
        latest = cursor.fetchone()
        if latest:
            print(f"\n🔄 Latest record:")
            print(f"   TX: {latest[0][:16]}...")
            print(f"   CPID: {latest[1]}")
            print(f"   Block: {latest[2]:,}")
            print(f"   Created: {latest[3]}")
        
        # Get distribution by type
        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN cpid LIKE 'A%' THEN 1 END) as cp_stamps,
                COUNT(CASE WHEN cpid NOT LIKE 'A%' THEN 1 END) as regular_stamps
            FROM sales_history
        """)
        dist = cursor.fetchone()
        print(f"\n📊 Distribution:")
        print(f"   CP Stamps (A...): {dist[0]:,}")
        print(f"   Regular Stamps: {dist[1]:,}")
        
        # Check for gaps
        cursor.execute("""
            SELECT MIN(block_index), MAX(block_index) 
            FROM sales_history
        """)
        min_block, max_block = cursor.fetchone()
        if min_block and max_block:
            print(f"\n📏 Block range: {min_block:,} - {max_block:,}")
            
            # Check processing rate
            cursor.execute("""
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as count
                FROM sales_history
                WHERE created_at >= NOW() - INTERVAL 7 DAY
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            """)
            print(f"\n📅 Processing rate (last 7 days):")
            for row in cursor.fetchall():
                print(f"   {row[0]}: {row[1]:,} records")
        
        # Check if actively processing
        cursor.execute("""
            SELECT COUNT(*) 
            FROM sales_history 
            WHERE created_at >= NOW() - INTERVAL 1 HOUR
        """)
        last_hour = cursor.fetchone()[0]
        
        if last_hour > 0:
            print(f"\n✅ Status: ACTIVE (processed {last_hour} records in last hour)")
        else:
            print("\n⚠️  Status: INACTIVE (no records processed in last hour)")
            
    except Exception as e:
        print(f"\n❌ Error checking sales history: {e}")
    finally:
        cursor.close()
        db.close()
    
    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    # Load environment variables
    dotenv_path = Path(__file__).parent.parent / ".env"
    load_dotenv(dotenv_path)
    
    check_sales_history_status()