#!/usr/bin/env python3
"""
Validate market data for all Counterparty stamps (non-SRC20).

This tool checks:
1. Last sale price from dispenser sales data
2. Floor price from open dispensers
3. Data completeness and accuracy
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

from src.index_core.database_manager import DatabaseManager
from src.index_core.fetch_utils import fetch_xcp


class StampMarketDataValidator:
    """Validator for stamp market data completeness."""

    def __init__(self):
        self.db_manager = DatabaseManager()
        self.cpid_cache = set()
        self.issues = {
            "missing_market_data": [],
            "missing_last_sale": [],
            "missing_floor_price": [],
            "stale_data": [],
            "data_mismatch": [],
        }

    def load_counterparty_stamps(self) -> int:
        """Load all Counterparty stamp CPIDs (non-SRC20)."""
        db = self.db_manager.connect()
        try:
            with db.cursor() as cursor:
                # Get all Counterparty stamps (those starting with 'A' and length > 15)
                cursor.execute(
                    """
                    SELECT DISTINCT cpid, stamp, ident 
                    FROM StampTableV4
                    WHERE cpid LIKE 'A%' 
                    AND LENGTH(cpid) > 15
                    AND ident NOT IN ('SRC-20', 'SRC-20 BALANCE')
                    ORDER BY cpid
                """
                )

                stamps = []
                for row in cursor.fetchall():
                    cpid = row[0]
                    self.cpid_cache.add(cpid)
                    stamps.append({"cpid": cpid, "stamp": row[1], "ident": row[2]})

                logger.info(f"Loaded {len(stamps):,} Counterparty stamps")
                return len(stamps)
        finally:
            db.close()

    def check_sales_data(self) -> Dict[str, int]:
        """Check sales history data for stamps."""
        db = self.db_manager.connect()
        stats = {"total_sales": 0, "unique_stamps_with_sales": 0, "stamps_without_sales": 0}

        try:
            with db.cursor() as cursor:
                # Get sales statistics
                cursor.execute(
                    """
                    SELECT 
                        COUNT(*) as total_sales,
                        COUNT(DISTINCT cpid) as unique_stamps
                    FROM stamp_sales_history
                    WHERE cpid IN (
                        SELECT cpid FROM StampTableV4 
                        WHERE cpid LIKE 'A%' 
                        AND LENGTH(cpid) > 15
                        AND ident NOT IN ('SRC-20', 'SRC-20 BALANCE')
                    )
                """
                )
                result = cursor.fetchone()
                stats["total_sales"] = result[0] or 0
                stats["unique_stamps_with_sales"] = result[1] or 0

                # Get stamps without any sales
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT cpid)
                    FROM StampTableV4
                    WHERE cpid LIKE 'A%' 
                    AND LENGTH(cpid) > 15
                    AND ident NOT IN ('SRC-20', 'SRC-20 BALANCE')
                    AND cpid NOT IN (
                        SELECT DISTINCT cpid FROM stamp_sales_history
                    )
                """
                )
                stats["stamps_without_sales"] = cursor.fetchone()[0] or 0

                logger.info(f"Sales data: {stats['total_sales']:,} sales for {stats['unique_stamps_with_sales']:,} stamps")
                logger.info(f"Stamps without sales: {stats['stamps_without_sales']:,}")

        finally:
            db.close()

        return stats

    def check_dispenser_data(self) -> Dict[str, int]:
        """Check current dispenser status for stamps from API."""
        stats = {"with_open_dispensers": 0, "total_dispensers": 0}

        logger.info("Fetching dispenser data from Counterparty API...")

        try:
            # Fetch open dispensers from API
            page = 0
            stamp_dispensers = {}

            while page < 10:  # Limit to first 10 pages for initial check
                params = {"status": "open", "limit": 1000}
                if page > 0:
                    params["offset"] = page * 1000

                result = fetch_xcp("/dispensers", params)

                if not result or "result" not in result:
                    break

                dispensers = result["result"]
                if not dispensers:
                    break

                # Filter for stamp assets
                for dispenser in dispensers:
                    asset = dispenser.get("asset")
                    if asset and asset in self.cpid_cache:
                        if asset not in stamp_dispensers:
                            stamp_dispensers[asset] = []
                        stamp_dispensers[asset].append(dispenser)
                        stats["total_dispensers"] += 1

                page += 1

                # Stop if we've found enough
                if len(dispensers) < 1000:
                    break

            stats["with_open_dispensers"] = len(stamp_dispensers)
            logger.info(
                f"Dispensers: {stats['with_open_dispensers']:,} stamps have {stats['total_dispensers']:,} open dispensers"
            )

        except Exception as e:
            logger.warning(f"Failed to fetch dispenser data: {e}")
            logger.info("Skipping dispenser validation")

        return stats

    def validate_market_data(self) -> Dict[str, List[Dict]]:
        """Validate market data for all stamps."""
        db = self.db_manager.connect()

        try:
            with db.cursor() as cursor:
                # Check for missing market data records
                cursor.execute(
                    """
                    SELECT s.cpid, s.stamp, s.ident
                    FROM StampTableV4 s
                    LEFT JOIN stamp_market_data m ON s.cpid = m.cpid
                    WHERE s.cpid LIKE 'A%' 
                    AND LENGTH(s.cpid) > 15
                    AND s.ident NOT IN ('SRC-20', 'SRC-20 BALANCE')
                    AND m.cpid IS NULL
                    LIMIT 100
                """
                )
                missing_records = []
                for row in cursor.fetchall():
                    missing_records.append({"cpid": row[0], "stamp": row[1], "ident": row[2]})

                if missing_records:
                    logger.warning(f"Found {len(missing_records)} stamps without market data records")
                    self.issues["missing_market_data"] = missing_records

                # Check for stamps with sales but no last sale price
                cursor.execute(
                    """
                    SELECT DISTINCT 
                        s.cpid, 
                        s.stamp,
                        COUNT(ssh.id) as sale_count,
                        MAX(ssh.block_index) as last_sale_block,
                        m.last_sale_price_btc
                    FROM StampTableV4 s
                    INNER JOIN stamp_sales_history ssh ON s.cpid = ssh.cpid
                    LEFT JOIN stamp_market_data m ON s.cpid = m.cpid
                    WHERE s.cpid LIKE 'A%' 
                    AND LENGTH(s.cpid) > 15
                    AND s.stamp_base != 'SRC-20'
                    AND (m.last_sale_price_btc IS NULL OR m.last_sale_price_btc = 0)
                    GROUP BY s.cpid, s.stamp, m.last_sale_price_btc
                    LIMIT 100
                """
                )
                missing_prices = []
                for row in cursor.fetchall():
                    missing_prices.append(
                        {
                            "cpid": row[0],
                            "stamp": row[1],
                            "sale_count": row[2],
                            "last_sale_block": row[3],
                            "market_data_price": row[4],
                        }
                    )

                if missing_prices:
                    logger.warning(f"Found {len(missing_prices)} stamps with sales but no last sale price")
                    self.issues["missing_last_sale"] = missing_prices

                # Check for stamps with open dispensers but no floor price
                cursor.execute(
                    """
                    SELECT DISTINCT 
                        s.cpid,
                        s.stamp,
                        COUNT(d.tx_index) as dispenser_count,
                        MIN(d.satoshirate) as min_rate,
                        m.floor_price_btc
                    FROM StampTableV4 s
                    INNER JOIN dispensers d ON s.cpid = d.asset
                    LEFT JOIN stamp_market_data m ON s.cpid = m.cpid
                    WHERE s.cpid LIKE 'A%' 
                    AND LENGTH(s.cpid) > 15
                    AND s.stamp_base != 'SRC-20'
                    AND d.status = 0  -- Open dispensers
                    AND (m.floor_price_btc IS NULL OR m.floor_price_btc = 0)
                    GROUP BY s.cpid, s.stamp, m.floor_price_btc
                    LIMIT 100
                """
                )
                missing_floors = []
                for row in cursor.fetchall():
                    missing_floors.append(
                        {
                            "cpid": row[0],
                            "stamp": row[1],
                            "dispenser_count": row[2],
                            "min_satoshirate": row[3],
                            "market_data_floor": row[4],
                        }
                    )

                if missing_floors:
                    logger.warning(f"Found {len(missing_floors)} stamps with open dispensers but no floor price")
                    self.issues["missing_floor_price"] = missing_floors

                # Check for stale data (not updated in 24 hours but has recent activity)
                cursor.execute(
                    """
                    SELECT 
                        s.cpid,
                        s.stamp,
                        m.last_updated,
                        MAX(ssh.block_index) as latest_sale_block,
                        MAX(ssh.processed_at) as latest_sale_time
                    FROM StampTableV4 s
                    INNER JOIN stamp_market_data m ON s.cpid = m.cpid
                    INNER JOIN stamp_sales_history ssh ON s.cpid = ssh.cpid
                    WHERE s.cpid LIKE 'A%' 
                    AND LENGTH(s.cpid) > 15
                    AND s.stamp_base != 'SRC-20'
                    AND m.last_updated < DATE_SUB(NOW(), INTERVAL 24 HOUR)
                    AND ssh.processed_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
                    GROUP BY s.cpid, s.stamp, m.last_updated
                    LIMIT 100
                """
                )
                stale_data = []
                for row in cursor.fetchall():
                    stale_data.append(
                        {
                            "cpid": row[0],
                            "stamp": row[1],
                            "last_updated": row[2],
                            "latest_sale_block": row[3],
                            "latest_sale_time": row[4],
                        }
                    )

                if stale_data:
                    logger.warning(f"Found {len(stale_data)} stamps with stale market data but recent sales")
                    self.issues["stale_data"] = stale_data

        finally:
            db.close()

        return self.issues

    def check_data_consistency(self, sample_size: int = 10):
        """Deep check on a sample of stamps for data consistency."""
        db = self.db_manager.connect()

        try:
            with db.cursor() as cursor:
                # Get a sample of stamps with both sales and market data
                cursor.execute(
                    """
                    SELECT DISTINCT s.cpid, s.stamp
                    FROM StampTableV4 s
                    INNER JOIN stamp_market_data m ON s.cpid = m.cpid
                    INNER JOIN stamp_sales_history ssh ON s.cpid = ssh.cpid
                    WHERE s.cpid LIKE 'A%' 
                    AND LENGTH(s.cpid) > 15
                    AND s.stamp_base != 'SRC-20'
                    ORDER BY RAND()
                    LIMIT %s
                """,
                    (sample_size,),
                )

                sample_stamps = cursor.fetchall()

                for cpid, stamp in sample_stamps:
                    # Get market data
                    cursor.execute(
                        """
                        SELECT 
                            last_sale_price_btc,
                            last_sale_block_index,
                            floor_price_btc,
                            volume_24h_btc,
                            volume_7d_btc,
                            last_updated
                        FROM stamp_market_data
                        WHERE cpid = %s
                    """,
                        (cpid,),
                    )
                    market_data = cursor.fetchone()

                    # Get actual sales data
                    cursor.execute(
                        """
                        SELECT 
                            MAX(block_index) as max_block,
                            MAX(btc_amount) / 100000000.0 as last_price,
                            SUM(CASE 
                                WHEN processed_at > DATE_SUB(NOW(), INTERVAL 24 HOUR) 
                                THEN btc_amount ELSE 0 
                            END) / 100000000.0 as vol_24h,
                            SUM(CASE 
                                WHEN processed_at > DATE_SUB(NOW(), INTERVAL 7 DAY) 
                                THEN btc_amount ELSE 0 
                            END) / 100000000.0 as vol_7d
                        FROM stamp_sales_history
                        WHERE cpid = %s
                    """,
                        (cpid,),
                    )
                    sales_data = cursor.fetchone()

                    # Get dispenser data
                    cursor.execute(
                        """
                        SELECT MIN(satoshirate) / 100000000.0 as min_rate
                        FROM dispensers
                        WHERE asset = %s AND status = 0
                    """,
                        (cpid,),
                    )
                    dispenser_data = cursor.fetchone()

                    # Compare data
                    issues = []

                    if market_data and sales_data:
                        if sales_data[0] and market_data[1] != sales_data[0]:
                            issues.append(f"Block mismatch: market={market_data[1]}, actual={sales_data[0]}")

                        if abs((market_data[3] or 0) - (sales_data[2] or 0)) > 0.00000001:
                            issues.append(f"24h volume mismatch: market={market_data[3]:.8f}, actual={sales_data[2]:.8f}")

                    if dispenser_data and dispenser_data[0]:
                        if not market_data[2] or abs(market_data[2] - dispenser_data[0]) > 0.00000001:
                            issues.append(f"Floor price mismatch: market={market_data[2]}, dispenser={dispenser_data[0]:.8f}")

                    if issues:
                        self.issues["data_mismatch"].append({"cpid": cpid, "stamp": stamp, "issues": issues})
                        logger.warning(f"Data inconsistency for {stamp} ({cpid}): {'; '.join(issues)}")

        finally:
            db.close()

    def generate_report(self):
        """Generate a comprehensive validation report."""
        print("\n" + "=" * 80)
        print("Bitcoin Stamps Market Data Validation Report")
        print("=" * 80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Load stamps
        total_stamps = self.load_counterparty_stamps()
        print(f"\nTotal Counterparty Stamps: {total_stamps:,}")

        # Check sales data
        print("\n📊 Sales History Data:")
        sales_stats = self.check_sales_data()
        for key, value in sales_stats.items():
            print(f"  {key.replace('_', ' ').title()}: {value:,}")

        # Check dispenser data
        print("\n🏪 Dispenser Data:")
        dispenser_stats = self.check_dispenser_data()
        for key, value in dispenser_stats.items():
            print(f"  {key.replace('_', ' ').title()}: {value:,}")

        # Validate market data
        print("\n🔍 Validating Market Data...")
        issues = self.validate_market_data()

        # Print issues summary
        print("\n⚠️  Issues Found:")
        for issue_type, items in issues.items():
            if items:
                print(f"\n{issue_type.replace('_', ' ').title()} ({len(items)} found):")
                # Show first 5 examples
                for item in items[:5]:
                    if issue_type == "missing_market_data":
                        print(f"  - {item['stamp']} ({item['cpid']})")
                    elif issue_type == "missing_last_sale":
                        print(
                            f"  - {item['stamp']} ({item['cpid']}) - {item['sale_count']} sales, last at block {item['last_sale_block']}"
                        )
                    elif issue_type == "missing_floor_price":
                        print(
                            f"  - {item['stamp']} ({item['cpid']}) - {item['dispenser_count']} dispensers, min rate: {item['min_satoshirate']} sats"
                        )
                    elif issue_type == "stale_data":
                        print(
                            f"  - {item['stamp']} ({item['cpid']}) - last updated: {item['last_updated']}, recent sale: {item['latest_sale_time']}"
                        )

                if len(items) > 5:
                    print(f"  ... and {len(items) - 5} more")

        # Check data consistency
        print("\n🔬 Checking Data Consistency (sample)...")
        self.check_data_consistency(sample_size=20)

        if self.issues["data_mismatch"]:
            print(f"\nData Mismatches ({len(self.issues['data_mismatch'])} found):")
            for item in self.issues["data_mismatch"][:5]:
                print(f"  - {item['stamp']} ({item['cpid']}):")
                for issue in item["issues"]:
                    print(f"    • {issue}")

        # Summary
        print("\n📋 Summary:")
        total_issues = sum(len(items) for items in issues.values())
        if total_issues == 0:
            print("✅ All market data appears to be complete and consistent!")
        else:
            print(f"❌ Found {total_issues} total issues across {len([k for k, v in issues.items() if v])} categories")
            print("\nRecommendations:")

            if issues["missing_market_data"]:
                print("  1. Run market data processor to create missing records")

            if issues["missing_last_sale"] or issues["missing_floor_price"]:
                print("  2. Ensure sales history processor is running and caught up")
                print("     Run: poetry run python tools/force_sales_history_catchup.py")

            if issues["stale_data"]:
                print("  3. Market data may need refresh for stamps with recent activity")

            if issues["data_mismatch"]:
                print("  4. Data inconsistencies found - may need to recalculate market data")
                print("     Run: poetry run python tools/debug/fix_activity_updates.py")

        print("\n" + "=" * 80)


def main():
    """Main entry point."""
    validator = StampMarketDataValidator()
    validator.generate_report()


if __name__ == "__main__":
    main()
