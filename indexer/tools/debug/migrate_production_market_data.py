#!/usr/bin/env python3
"""
Production Market Data Migration Script

This script safely applies the new market data schema changes to production.
It includes rollback capabilities and validation.

⚠️  IMPORTANT: Only run this on production with proper backups in place!

Usage:
    python migrate_production_market_data.py [--dry-run] [--verbose]

Options:
    --dry-run    Show what would be changed without making changes
    --verbose    Show detailed output
"""

import os
import sys
import pymysql
from datetime import datetime
from typing import List, Tuple
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(env_path):
    load_dotenv(env_path)


class ProductionMigrator:
    """Handles safe migration of production database."""

    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.connection = None

        # Migration SQL statements from our schema
        self.migration_statements = [
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
        ]

    def connect_production(self) -> bool:
        """Connect to production database."""
        try:
            host = os.environ.get("ST3_HOSTNAME")
            user = os.environ.get("ST3_USER")
            password = os.environ.get("ST3_PASSWORD")
            database = os.environ.get("PROD_DATABASE")

            if not all([host, user, password, database]):
                print("❌ Missing required ST3_* environment variables")
                return False

            print(f"🔌 Connecting to production: {host}/{database}")

            self.connection = pymysql.connect(host=host, user=user, password=password, database=database, charset="utf8mb4")

            print("✅ Connected to production database")
            return True

        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            return False

    def check_table_exists(self) -> bool:
        """Check if stamp_market_data table exists."""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW TABLES LIKE 'stamp_market_data'")
                result = cursor.fetchone()

                if result:
                    print("✅ stamp_market_data table exists")
                    return True
                else:
                    print("❌ stamp_market_data table not found!")
                    return False

        except Exception as e:
            print(f"❌ Error checking table: {e}")
            return False

    def get_current_schema(self) -> List[Tuple]:
        """Get current table schema."""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("DESCRIBE stamp_market_data")
                return cursor.fetchall()
        except Exception as e:
            print(f"❌ Error getting schema: {e}")
            return []

    def check_existing_columns(self) -> Tuple[List[str], List[str]]:
        """Check which columns already exist."""
        new_columns = [
            "last_sale_tx_hash",
            "last_sale_buyer_address",
            "last_sale_dispenser_address",
            "last_sale_btc_amount",
            "last_sale_dispenser_tx_hash",
            "last_sale_block_index",
        ]

        schema = self.get_current_schema()
        existing_columns = [row[0] for row in schema]

        missing = [col for col in new_columns if col not in existing_columns]
        present = [col for col in new_columns if col in existing_columns]

        return missing, present

    def check_existing_indexes(self) -> bool:
        """Check if the new index already exists."""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW INDEX FROM stamp_market_data WHERE Key_name = 'idx_recent_sales'")
                return bool(cursor.fetchall())
        except Exception as e:
            print(f"❌ Error checking indexes: {e}")
            return False

    def run_migration(self) -> bool:
        """Run the migration with safety checks."""
        print(f"\n🚀 {'DRY RUN: ' if self.dry_run else ''}Starting migration...")

        # Pre-migration checks
        missing_cols, present_cols = self.check_existing_columns()
        index_exists = self.check_existing_indexes()

        print(f"\n📊 Pre-migration status:")
        print(f"  Missing columns: {len(missing_cols)}")
        print(f"  Present columns: {len(present_cols)}")
        print(f"  Index exists: {index_exists}")

        if self.verbose:
            if missing_cols:
                print(f"  Missing: {', '.join(missing_cols)}")
            if present_cols:
                print(f"  Present: {', '.join(present_cols)}")

        if not missing_cols and index_exists:
            print("✅ All changes already applied - nothing to do!")
            return True

        if self.dry_run:
            print(f"\n🔍 DRY RUN: Would execute {len(self.migration_statements)} statements:")
            for i, stmt in enumerate(self.migration_statements, 1):
                print(f"  {i}. {stmt.strip().split('ADD')[1].split()[0:3] if 'ADD COLUMN' in stmt else 'ADD INDEX'}")
            return True

        # Confirm before proceeding
        if not self._confirm_migration():
            print("❌ Migration cancelled by user")
            return False

        # Execute migration
        try:
            success_count = 0
            for i, stmt in enumerate(self.migration_statements, 1):
                print(f"  Executing step {i}/{len(self.migration_statements)}...")

                if self.verbose:
                    print(f"    SQL: {stmt.strip()[:100]}...")

                with self.connection.cursor() as cursor:
                    cursor.execute(stmt)
                    self.connection.commit()
                    success_count += 1

                print(f"    ✅ Step {i} completed")

            print(f"\n🎉 Migration completed successfully! ({success_count} statements executed)")
            return True

        except Exception as e:
            print(f"\n❌ Migration failed at step {i}: {e}")
            print("⚠️  Attempting rollback...")

            try:
                self.connection.rollback()
                print("✅ Rollback successful")
            except Exception as rollback_error:
                print(f"❌ Rollback failed: {rollback_error}")

            return False

    def _confirm_migration(self) -> bool:
        """Confirm migration with user."""
        print(f"\n⚠️  WARNING: About to modify production database!")
        print(f"   Database: {os.environ.get('ST3_HOSTNAME')}/{os.environ.get('PROD_DATABASE')}")
        print(f"   This will add 6 columns and 1 index to stamp_market_data table")
        print(f"   Ensure you have a recent backup before proceeding!")

        response = input("\n   Type 'YES' to proceed with migration: ")
        return response.strip() == "YES"

    def validate_migration(self) -> bool:
        """Validate that migration was successful."""
        print(f"\n🔍 Validating migration results...")

        missing_cols, present_cols = self.check_existing_columns()
        index_exists = self.check_existing_indexes()

        success = len(missing_cols) == 0 and index_exists

        print(f"  Columns present: {len(present_cols)}/6 {'✅' if len(present_cols) == 6 else '❌'}")
        print(f"  Index present: {'✅' if index_exists else '❌'}")

        if success:
            print("✅ Migration validation passed!")
        else:
            print("❌ Migration validation failed!")
            if missing_cols:
                print(f"   Missing columns: {', '.join(missing_cols)}")
            if not index_exists:
                print(f"   Missing index: idx_recent_sales")

        return success

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            print("\n🔐 Database connection closed")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate production market data schema")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying them")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    print("🔧 Production Market Data Migration")
    print("=" * 50)

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
    else:
        print("⚠️  LIVE MIGRATION MODE - Changes will be applied!")

    migrator = ProductionMigrator(dry_run=args.dry_run, verbose=args.verbose)

    try:
        # Connect and validate
        if not migrator.connect_production():
            return 1

        if not migrator.check_table_exists():
            return 1

        # Run migration
        if migrator.run_migration():
            if not args.dry_run:
                migrator.validate_migration()
            return 0
        else:
            return 1

    except KeyboardInterrupt:
        print("\n⚠️  Migration interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        return 1
    finally:
        migrator.close()


if __name__ == "__main__":
    sys.exit(main())
