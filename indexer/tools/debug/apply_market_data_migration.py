#!/usr/bin/env python3
"""
Apply Market Data Migration to Production

This script applies the specific ALTER TABLE statements for the new market data fields
since the indexer skips schema execution when all tables already exist.

Usage:
    python apply_market_data_migration.py [--dry-run] [--verbose]

Environment Variables Required:
    ST3_HOSTNAME, ST3_USER, ST3_PASSWORD, PROD_DATABASE
"""

import os
import sys
import pymysql
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(env_path):
    load_dotenv(env_path)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Apply market data migration to production")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying them")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    print("🔧 Market Data Migration Application")
    print("=" * 50)

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
    else:
        print("⚠️  LIVE MODE - Changes will be applied!")

    # Connect to production
    try:
        host = os.environ.get("ST3_HOSTNAME")
        user = os.environ.get("ST3_USER")
        password = os.environ.get("ST3_PASSWORD")
        database = os.environ.get("PROD_DATABASE")

        if not all([host, user, password, database]):
            print("❌ Missing required ST3_* environment variables")
            return 1

        print(f"🔌 Connecting to production: {host}/{database}")

        connection = pymysql.connect(host=host, user=user, password=password, database=database, charset="utf8mb4")

        print("✅ Connected to production database")

        # Migration statements
        migration_statements = [
            """
            ALTER TABLE `stamp_market_data` 
            ADD COLUMN IF NOT EXISTS `last_sale_block_index` INTEGER NULL 
            COMMENT 'Block index of the most recent sale' 
            AFTER `last_price_update`
            """,
            """
            ALTER TABLE `stamp_market_data` 
            ADD INDEX IF NOT EXISTS `idx_recent_sales` (`last_price_update` DESC, `volume_24h_btc` DESC) 
            COMMENT 'For recent sales filtering and sorting'
            """,
            """
            ALTER TABLE `stamp_market_data` 
            ADD COLUMN IF NOT EXISTS `last_sale_tx_hash` VARCHAR(64) NULL 
            COMMENT 'Transaction hash of the most recent sale' 
            AFTER `confidence_level`
            """,
            """
            ALTER TABLE `stamp_market_data` 
            ADD COLUMN IF NOT EXISTS `last_sale_buyer_address` VARCHAR(100) NULL 
            COMMENT 'Address of the buyer in the most recent sale' 
            AFTER `last_sale_tx_hash`
            """,
            """
            ALTER TABLE `stamp_market_data` 
            ADD COLUMN IF NOT EXISTS `last_sale_dispenser_address` VARCHAR(100) NULL 
            COMMENT 'Dispenser address used in the most recent sale' 
            AFTER `last_sale_buyer_address`
            """,
            """
            ALTER TABLE `stamp_market_data` 
            ADD COLUMN IF NOT EXISTS `last_sale_btc_amount` BIGINT NULL 
            COMMENT 'Actual BTC amount paid in satoshis for the most recent sale' 
            AFTER `last_sale_dispenser_address`
            """,
            """
            ALTER TABLE `stamp_market_data` 
            ADD COLUMN IF NOT EXISTS `last_sale_dispenser_tx_hash` VARCHAR(64) NULL 
            COMMENT 'Transaction hash that created the dispenser (optional)' 
            AFTER `last_sale_btc_amount`
            """,
        ]

        if args.dry_run:
            print(f"\n🔍 DRY RUN: Would execute {len(migration_statements)} statements:")
            for i, stmt in enumerate(migration_statements, 1):
                stmt_type = "ADD INDEX" if "ADD INDEX" in stmt else "ADD COLUMN"
                field_name = stmt.split("`")[-2] if "`" in stmt else "idx_recent_sales"
                print(f"  {i}. {stmt_type}: {field_name}")
            print("\nRun without --dry-run to apply these changes")
            return 0

        # Confirm before proceeding
        print(f"\n⚠️  WARNING: About to modify production database!")
        print(f"   Database: {host}/{database}")
        print(f"   This will add 6 columns and 1 index to stamp_market_data table")
        print(f"   Ensure you have a recent backup before proceeding!")

        response = input("\n   Type 'YES' to proceed with migration: ")
        if response.strip() != "YES":
            print("❌ Migration cancelled by user")
            return 1

        # Execute migration
        success_count = 0
        with connection.cursor() as cursor:
            for i, stmt in enumerate(migration_statements, 1):
                print(f"  Executing step {i}/{len(migration_statements)}...")

                if args.verbose:
                    print(f"    SQL: {stmt.strip()}")

                try:
                    cursor.execute(stmt)
                    connection.commit()
                    success_count += 1
                    print(f"    ✅ Step {i} completed")
                except Exception as e:
                    print(f"    ⚠️  Step {i}: {e}")
                    # Continue with other statements since IF NOT EXISTS should handle conflicts
                    continue

        print(f"\n🎉 Migration completed! ({success_count}/{len(migration_statements)} statements executed)")

        # Validate results
        print(f"\n🔍 Validating migration results...")
        with connection.cursor() as cursor:
            cursor.execute("DESCRIBE stamp_market_data")
            columns = [row[0] for row in cursor.fetchall()]

            new_columns = [
                "last_sale_tx_hash",
                "last_sale_buyer_address",
                "last_sale_dispenser_address",
                "last_sale_btc_amount",
                "last_sale_dispenser_tx_hash",
                "last_sale_block_index",
            ]

            present = [col for col in new_columns if col in columns]
            missing = [col for col in new_columns if col not in columns]

            print(f"  Columns present: {len(present)}/6")
            if args.verbose:
                for col in present:
                    print(f"    ✅ {col}")
                for col in missing:
                    print(f"    ❌ {col}")

            # Check index
            cursor.execute("SHOW INDEX FROM stamp_market_data WHERE Key_name = 'idx_recent_sales'")
            index_exists = bool(cursor.fetchall())
            print(f"  Index present: {'✅' if index_exists else '❌'}")

            if len(present) == 6 and index_exists:
                print("✅ Migration validation passed!")
            else:
                print("❌ Migration validation failed!")

        connection.close()
        print("\n🔐 Database connection closed")

        return 0

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
