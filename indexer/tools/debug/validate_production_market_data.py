#!/usr/bin/env python3
"""
Production Market Data Validation Script

This script validates that the production database is properly populating
the new recent sales market data fields we added for the frontend team.

IMPORTANT: The new schema fields are automatically applied when the indexer
starts up. If fields are missing, simply restart the indexer and they will
be added via the ALTER TABLE statements in table_schema.sql.

Usage:
    python validate_production_market_data.py [--verbose] [--limit N]

Environment Variables Required:
    RDS_HOSTNAME, RDS_USER, RDS_PASSWORD, RDS_DATABASE
"""

import os
import sys
import pymysql
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(env_path):
    load_dotenv(env_path)


class MarketDataValidator:
    """Validates market data fields in production database."""

    def __init__(self):
        self.verbose = False
        self.connection = None

    def connect_production(self) -> bool:
        """Connect to production database using RDS_* environment variables."""
        try:
            host = os.environ.get("RDS_HOSTNAME")
            user = os.environ.get("RDS_USER")
            password = os.environ.get("RDS_PASSWORD")
            database = os.environ.get("RDS_DATABASE")

            if not all([host, user, password, database]):
                print("❌ Missing required RDS_* environment variables")
                print("Required: RDS_HOSTNAME, RDS_USER, RDS_PASSWORD, RDS_DATABASE")
                return False

            print(f"🔌 Connecting to production database: {host}/{database}")

            self.connection = pymysql.connect(host=host, user=user, password=password, database=database, charset="utf8mb4")

            print("✅ Connected to production database")
            return True

        except Exception as e:
            print(f"❌ Failed to connect to production database: {e}")
            return False

    def check_schema_exists(self) -> bool:
        """Check if the new market data columns exist in production."""
        print("\n📋 Checking schema for new market data fields...")

        new_fields = [
            "last_sale_tx_hash",
            "last_sale_buyer_address",
            "last_sale_dispenser_address",
            "last_sale_btc_amount",
            "last_sale_dispenser_tx_hash",
            "last_sale_block_index",
        ]

        try:
            with self.connection.cursor() as cursor:
                cursor.execute("DESCRIBE stamp_market_data")
                existing_columns = [row[0] for row in cursor.fetchall()]

                missing_fields = []
                for field in new_fields:
                    if field in existing_columns:
                        print(f"  ✅ {field}")
                    else:
                        print(f"  ❌ {field} - MISSING")
                        missing_fields.append(field)

                if missing_fields:
                    print(f"\n⚠️  WARNING: {len(missing_fields)} fields are missing from production")
                    print("   You may need to run the database migration")
                    return False
                else:
                    print("\n✅ All new market data fields exist in production schema")
                    return True

        except Exception as e:
            print(f"❌ Error checking schema: {e}")
            return False

    def check_index_exists(self) -> bool:
        """Check if the idx_recent_sales index exists."""
        print("\n📊 Checking for idx_recent_sales index...")

        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW INDEX FROM stamp_market_data WHERE Key_name = 'idx_recent_sales'")
                result = cursor.fetchall()

                if result:
                    print("  ✅ idx_recent_sales index exists")
                    if self.verbose:
                        for row in result:
                            print(f"    Column: {row[4]}, Seq: {row[3]}")
                    return True
                else:
                    print("  ❌ idx_recent_sales index is missing")
                    return False

        except Exception as e:
            print(f"❌ Error checking index: {e}")
            return False

    def analyze_market_data_population(self, limit: int = 50) -> Dict:
        """Analyze how well the market data is being populated."""
        print(f"\n📈 Analyzing market data population (limit: {limit})...")

        try:
            with self.connection.cursor() as cursor:
                # Get basic stats
                cursor.execute("SELECT COUNT(*) FROM stamp_market_data")
                total_records = cursor.fetchone()[0]

                # Check how many have recent sales data
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM stamp_market_data 
                    WHERE last_price_update IS NOT NULL
                """
                )
                records_with_sales = cursor.fetchone()[0]

                # Check new fields population
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM stamp_market_data 
                    WHERE last_sale_tx_hash IS NOT NULL
                """
                )
                records_with_tx_hash = cursor.fetchone()[0]

                cursor.execute(
                    """
                    SELECT COUNT(*) FROM stamp_market_data 
                    WHERE last_sale_buyer_address IS NOT NULL
                """
                )
                records_with_buyer = cursor.fetchone()[0]

                cursor.execute(
                    """
                    SELECT COUNT(*) FROM stamp_market_data 
                    WHERE last_sale_btc_amount IS NOT NULL
                """
                )
                records_with_amount = cursor.fetchone()[0]

                # Get sample of recent sales
                cursor.execute(
                    """
                    SELECT 
                        cpid,
                        recent_sale_price_btc,
                        last_price_update,
                        last_sale_tx_hash,
                        last_sale_buyer_address,
                        last_sale_dispenser_address,
                        last_sale_btc_amount,
                        last_sale_block_index
                    FROM stamp_market_data 
                    WHERE last_price_update IS NOT NULL
                    ORDER BY last_price_update DESC
                    LIMIT %s
                """,
                    (limit,),
                )

                recent_sales = cursor.fetchall()

                stats = {
                    "total_records": total_records,
                    "records_with_sales": records_with_sales,
                    "records_with_tx_hash": records_with_tx_hash,
                    "records_with_buyer": records_with_buyer,
                    "records_with_amount": records_with_amount,
                    "recent_sales": recent_sales,
                }

                self._print_population_stats(stats)
                return stats

        except Exception as e:
            print(f"❌ Error analyzing market data: {e}")
            return {}

    def _print_population_stats(self, stats: Dict):
        """Print formatted population statistics."""
        total = stats["total_records"]
        sales = stats["records_with_sales"]
        tx_hash = stats["records_with_tx_hash"]
        buyer = stats["records_with_buyer"]
        amount = stats["records_with_amount"]

        print(f"\n📊 Market Data Population Statistics:")
        print(f"  Total stamp market records: {total:,}")
        print(f"  Records with sales data: {sales:,} ({(sales/total*100):.1f}%)")
        print(f"  Records with tx_hash: {tx_hash:,} ({(tx_hash/total*100):.1f}%)")
        print(f"  Records with buyer address: {buyer:,} ({(buyer/total*100):.1f}%)")
        print(f"  Records with BTC amount: {amount:,} ({(amount/total*100):.1f}%)")

        if sales > 0:
            completeness = min(tx_hash, buyer, amount) / sales * 100
            print(f"  New fields completeness: {completeness:.1f}%")

            if completeness < 50:
                print("  ⚠️  WARNING: Low completeness for new fields")
            elif completeness < 90:
                print("  🟡 Moderate completeness for new fields")
            else:
                print("  ✅ Good completeness for new fields")

    def show_recent_sales_sample(self, limit: int = 10):
        """Show a sample of recent sales with all the new fields."""
        print(f"\n🔍 Sample Recent Sales (limit: {limit}):")

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 
                        cpid,
                        recent_sale_price_btc,
                        last_price_update,
                        last_sale_tx_hash,
                        last_sale_buyer_address,
                        last_sale_dispenser_address,
                        last_sale_btc_amount,
                        last_sale_block_index,
                        last_sale_dispenser_tx_hash
                    FROM stamp_market_data 
                    WHERE last_price_update IS NOT NULL
                    ORDER BY last_price_update DESC
                    LIMIT %s
                """,
                    (limit,),
                )

                sales = cursor.fetchall()

                if not sales:
                    print("  ❌ No recent sales found")
                    return

                for i, sale in enumerate(sales, 1):
                    cpid, price, timestamp, tx_hash, buyer, dispenser, btc_amount, block_idx, dispenser_tx = sale

                    print(f"\n  {i}. CPID: {cpid}")
                    print(f"     Price: {price} BTC")
                    print(f"     Time: {timestamp}")
                    print(f"     TX Hash: {tx_hash or 'NULL'}")
                    print(f"     Buyer: {buyer or 'NULL'}")
                    print(f"     Dispenser: {dispenser or 'NULL'}")
                    print(f"     BTC Amount: {btc_amount or 'NULL'} sats")
                    print(f"     Block: {block_idx or 'NULL'}")
                    print(f"     Dispenser TX: {dispenser_tx or 'NULL'}")

                    # Validate data completeness for this record
                    missing_fields = []
                    if not tx_hash:
                        missing_fields.append("tx_hash")
                    if not buyer:
                        missing_fields.append("buyer_address")
                    if not btc_amount:
                        missing_fields.append("btc_amount")
                    if not block_idx:
                        missing_fields.append("block_index")

                    if missing_fields:
                        print(f"     ⚠️  Missing: {', '.join(missing_fields)}")
                    else:
                        print(f"     ✅ Complete data")

        except Exception as e:
            print(f"❌ Error showing recent sales: {e}")

    def validate_data_consistency(self):
        """Validate data consistency and relationships."""
        print(f"\n🔍 Validating data consistency...")

        try:
            with self.connection.cursor() as cursor:
                # Check for records with sales but missing new fields
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM stamp_market_data 
                    WHERE last_price_update IS NOT NULL 
                    AND (last_sale_tx_hash IS NULL 
                         OR last_sale_buyer_address IS NULL 
                         OR last_sale_btc_amount IS NULL)
                """
                )
                inconsistent_records = cursor.fetchone()[0]

                # Check for impossible data combinations
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM stamp_market_data 
                    WHERE last_sale_btc_amount < 0
                """
                )
                negative_amounts = cursor.fetchone()[0]

                cursor.execute(
                    """
                    SELECT COUNT(*) FROM stamp_market_data 
                    WHERE last_sale_block_index < 0
                """
                )
                negative_blocks = cursor.fetchone()[0]

                # Check for very recent data (last 24 hours)
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM stamp_market_data 
                    WHERE last_price_update > DATE_SUB(NOW(), INTERVAL 24 HOUR)
                """
                )
                recent_updates = cursor.fetchone()[0]

                print(f"  Records with sales but missing new fields: {inconsistent_records}")
                print(f"  Records with negative BTC amounts: {negative_amounts}")
                print(f"  Records with negative block numbers: {negative_blocks}")
                print(f"  Records updated in last 24 hours: {recent_updates}")

                issues = inconsistent_records + negative_amounts + negative_blocks
                if issues == 0:
                    print("  ✅ No data consistency issues found")
                else:
                    print(f"  ⚠️  Found {issues} potential data consistency issues")

                if recent_updates > 0:
                    print(f"  ✅ Recent activity detected ({recent_updates} updates in 24h)")
                else:
                    print(f"  ⚠️  No recent market data updates (may indicate job not running)")

        except Exception as e:
            print(f"❌ Error validating consistency: {e}")

    def diagnose_market_data_jobs(self) -> Dict[str, Any]:
        """Diagnose why market data jobs might not be working."""
        print(f"\n🔧 Diagnosing market data job execution...")
        diagnosis = {}

        try:
            with self.connection.cursor() as cursor:
                # Check if we have any stamps that should need updates
                cursor.execute(
                    """
                    SELECT COUNT(*) as total_stamps,
                           COUNT(CASE WHEN ident IN ('STAMP', 'SRC-721') THEN 1 END) as eligible_stamps,
                           COUNT(CASE WHEN ident IN ('STAMP', 'SRC-721') AND smd.cpid IS NULL THEN 1 END) as never_processed
                    FROM StampTableV4 s
                    LEFT JOIN stamp_market_data smd ON s.cpid = smd.cpid
                """
                )
                stamp_analysis = cursor.fetchone()

                if stamp_analysis:
                    total, eligible, never_processed = stamp_analysis
                    print(f"  📊 Stamp Analysis:")
                    print(f"    Total stamps: {total:,}")
                    print(f"    Eligible for market data: {eligible:,}")
                    print(f"    Never processed: {never_processed:,}")

                    diagnosis["stamp_analysis"] = {
                        "total_stamps": total,
                        "eligible_stamps": eligible,
                        "never_processed": never_processed,
                    }

                # Check recent activity in stamp table
                cursor.execute(
                    """
                    SELECT COUNT(*) as recent_stamps
                    FROM StampTableV4 s
                    WHERE s.block_time > DATE_SUB(NOW(), INTERVAL 7 DAY)
                    AND s.ident IN ('STAMP', 'SRC-721')
                """
                )
                recent_stamps = cursor.fetchone()[0]
                print(f"    New stamps (last 7 days): {recent_stamps:,}")
                diagnosis["recent_activity"] = recent_stamps

                # Check for existing market data tables
                cursor.execute("SHOW TABLES LIKE '%market_data%'")
                market_tables = cursor.fetchall()
                print(f"\n  📋 Market Data Tables:")
                for table in market_tables:
                    table_name = table[0]
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    print(f"    {table_name}: {count:,} records")

                # Check if there are any recent job runs (look for patterns in last_updated)
                cursor.execute(
                    """
                    SELECT 
                        DATE_FORMAT(last_updated, '%Y-%m-%d %H:%i') as update_time,
                        COUNT(*) as batch_size
                    FROM stamp_market_data 
                    WHERE last_updated IS NOT NULL
                    GROUP BY DATE_FORMAT(last_updated, '%Y-%m-%d %H:%i')
                    ORDER BY update_time DESC
                    LIMIT 10
                """
                )
                recent_batches = cursor.fetchall()

                if recent_batches:
                    print(f"\n  🕒 Recent Batch Processing:")
                    for batch_time, batch_size in recent_batches:
                        print(f"    {batch_time}: {batch_size} records updated")
                    diagnosis["recent_batches"] = recent_batches
                else:
                    print(f"\n  ⚠️  No batch processing detected")
                    diagnosis["recent_batches"] = []

        except Exception as e:
            print(f"❌ Error during diagnosis: {e}")
            diagnosis["error"] = str(e)

        return diagnosis

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            print("\n🔐 Database connection closed")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Validate production market data fields")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--limit", "-l", type=int, default=10, help="Limit for sample queries")

    args = parser.parse_args()

    validator = MarketDataValidator()
    validator.verbose = args.verbose

    print("🔍 Production Market Data Validation")
    print("=" * 50)

    # Connect to production
    if not validator.connect_production():
        return 1

    try:
        # Run all validations
        schema_ok = validator.check_schema_exists()
        index_ok = validator.check_index_exists()

        if not schema_ok:
            print("\n❌ Schema validation failed - migration may be needed")
            return 1

        # Analyze data population
        stats = validator.analyze_market_data_population(limit=args.limit * 5)

        # Show sample data
        validator.show_recent_sales_sample(limit=args.limit)

        # Validate consistency
        validator.validate_data_consistency()

        # Diagnose job execution issues
        validator.diagnose_market_data_jobs()

        print("\n" + "=" * 50)
        print("📋 VALIDATION SUMMARY")
        print("=" * 50)

        if schema_ok and index_ok:
            print("✅ Schema: All required fields and indexes present")
        else:
            print("❌ Schema: Missing fields or indexes")

        if stats and stats.get("records_with_sales", 0) > 0:
            total = stats["total_records"]
            sales = stats["records_with_sales"]
            completeness = (
                min(stats["records_with_tx_hash"], stats["records_with_buyer"], stats["records_with_amount"]) / sales * 100
                if sales > 0
                else 0
            )

            print(f"✅ Data: {sales:,} stamps have sales data ({sales/total*100:.1f}% of total)")
            print(f"{'✅' if completeness > 90 else '⚠️ '} Completeness: {completeness:.1f}% for new fields")
        else:
            print("❌ Data: No sales data found")

        print("\n🎯 Production database validation complete!")

        return 0

    except KeyboardInterrupt:
        print("\n⚠️  Validation interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Validation failed: {e}")
        return 1
    finally:
        validator.close()


if __name__ == "__main__":
    sys.exit(main())
