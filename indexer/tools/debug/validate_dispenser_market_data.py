#!/usr/bin/env python3
"""
Comprehensive validation tool for stamps with dispenser activity.

This tool:
1. Fetches all stamps that have ever had dispenser activity
2. Checks current open dispensers from API
3. Validates market data is properly populated
4. Identifies gaps and inconsistencies
"""

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

from src.index_core.database_manager import DatabaseManager
from src.index_core.fetch_utils import RateLimiter, fetch_xcp


class DispenserMarketDataValidator:
    """Validator for stamps with dispenser activity."""

    def __init__(self):
        self.db_manager = DatabaseManager()
        self.rate_limiter = RateLimiter(calls_per_second=1.0)
        self.cpid_cache: Set[str] = set()
        self.dispenser_data: Dict[str, Dict] = {}
        self.historical_dispenses: Dict[str, List] = {}

    def load_stamp_cpids(self) -> int:
        """Load all Counterparty stamp CPIDs."""
        db = self.db_manager.connect()
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT cpid
                    FROM StampTableV4
                    WHERE cpid LIKE 'A%' 
                    AND LENGTH(cpid) > 15
                    AND ident NOT IN ('SRC-20', 'SRC-20 BALANCE')
                    """
                )

                for row in cursor.fetchall():
                    self.cpid_cache.add(row[0])

                logger.info(f"Loaded {len(self.cpid_cache):,} Counterparty stamp CPIDs")
                return len(self.cpid_cache)
        finally:
            db.close()

    def fetch_open_dispensers(self) -> int:
        """Fetch all open dispensers from Counterparty API."""
        logger.info("Fetching open dispensers from API...")

        try:
            cursor = None
            page = 0
            total_dispensers = 0
            stamp_dispensers = 0

            while page < 100:  # Safety limit
                self.rate_limiter.acquire()

                params = {"status": "open", "limit": 1000, "verbose": True}
                if cursor:
                    params["cursor"] = cursor

                logger.debug(f"Fetching dispensers page {page + 1}")
                response = fetch_xcp("/dispensers", params)

                if not response or "result" not in response:
                    logger.error(f"Failed to fetch dispensers page {page + 1}")
                    break

                dispensers = response["result"]
                if not dispensers:
                    logger.info(f"No more dispensers after page {page}")
                    break

                total_dispensers += len(dispensers)

                # Filter for stamp assets
                for dispenser in dispensers:
                    asset = dispenser.get("asset")
                    if asset and asset in self.cpid_cache:
                        if asset not in self.dispenser_data:
                            self.dispenser_data[asset] = {"dispensers": [], "min_satoshirate": None, "total_give_remaining": 0}

                        self.dispenser_data[asset]["dispensers"].append(dispenser)
                        satoshirate = dispenser.get("satoshirate", 0)

                        # Track minimum rate
                        if self.dispenser_data[asset]["min_satoshirate"] is None:
                            self.dispenser_data[asset]["min_satoshirate"] = satoshirate
                        else:
                            self.dispenser_data[asset]["min_satoshirate"] = min(
                                self.dispenser_data[asset]["min_satoshirate"], satoshirate
                            )

                        # Sum give_remaining
                        self.dispenser_data[asset]["total_give_remaining"] += dispenser.get("give_remaining", 0)
                        stamp_dispensers += 1

                page += 1
                cursor = response.get("next_cursor")

                if not cursor:
                    break

                # Progress log every 10 pages
                if page % 10 == 0:
                    logger.info(
                        f"Processed {page} pages, {total_dispensers:,} total dispensers, {stamp_dispensers:,} stamp dispensers"
                    )

            logger.info(f"Fetched {total_dispensers:,} total dispensers, {stamp_dispensers:,} for stamps")
            logger.info(f"Found {len(self.dispenser_data):,} stamps with open dispensers")

            return len(self.dispenser_data)

        except Exception as e:
            logger.error(f"Error fetching dispensers: {e}")
            return 0

    def fetch_historical_dispenses(self, sample_size: int = 1000) -> int:
        """Fetch sample of historical dispenses to find stamps with past activity."""
        logger.info(f"Fetching sample of {sample_size:,} historical dispenses...")

        try:
            cursor = None
            page = 0
            total_dispenses = 0
            stamp_dispenses = 0

            while total_dispenses < sample_size and page < 10:
                self.rate_limiter.acquire()

                params = {"limit": 1000, "verbose": True}
                if cursor:
                    params["cursor"] = cursor

                response = fetch_xcp("/dispenses", params)

                if not response or "result" not in response:
                    break

                dispenses = response["result"]
                if not dispenses:
                    break

                for dispense in dispenses:
                    asset = dispense.get("asset")
                    if asset and asset in self.cpid_cache:
                        if asset not in self.historical_dispenses:
                            self.historical_dispenses[asset] = []
                        self.historical_dispenses[asset].append(dispense)
                        stamp_dispenses += 1

                    total_dispenses += 1
                    if total_dispenses >= sample_size:
                        break

                page += 1
                cursor = response.get("next_cursor")

                if not cursor:
                    break

            logger.info(f"Sampled {total_dispenses:,} dispenses, found {stamp_dispenses:,} for stamps")
            logger.info(f"Found {len(self.historical_dispenses):,} stamps with historical dispenses")

            return len(self.historical_dispenses)

        except Exception as e:
            logger.error(f"Error fetching historical dispenses: {e}")
            return 0

    def validate_market_data(self) -> Dict[str, List]:
        """Validate market data for stamps with dispenser activity."""
        db = self.db_manager.connect()
        issues = {
            "missing_floor_price": [],
            "incorrect_floor_price": [],
            "missing_recent_sale": [],
            "stale_floor_price": [],
            "no_market_data": [],
        }

        try:
            # Get all stamps with dispenser activity
            stamps_with_activity = set(self.dispenser_data.keys()) | set(self.historical_dispenses.keys())
            logger.info(f"Validating market data for {len(stamps_with_activity):,} stamps with dispenser activity")

            for cpid in stamps_with_activity:
                with db.cursor() as cursor:
                    # Get market data
                    cursor.execute(
                        """
                        SELECT 
                            floor_price_btc,
                            recent_sale_price_btc,
                            last_updated,
                            volume_24h_btc,
                            activity_level
                        FROM stamp_market_data
                        WHERE cpid = %s
                        """,
                        (cpid,),
                    )
                    market_data = cursor.fetchone()

                    # Get stamp info
                    cursor.execute("SELECT stamp FROM StampTableV4 WHERE cpid = %s", (cpid,))
                    stamp_info = cursor.fetchone()
                    stamp_name = stamp_info[0] if stamp_info else cpid

                    # Check if market data exists
                    if not market_data:
                        issues["no_market_data"].append(
                            {
                                "cpid": cpid,
                                "stamp": stamp_name,
                                "has_open_dispensers": cpid in self.dispenser_data,
                                "has_historical": cpid in self.historical_dispenses,
                            }
                        )
                        continue

                    floor_price, sale_price, last_updated, volume_24h, activity = market_data

                    # Validate open dispensers
                    if cpid in self.dispenser_data:
                        dispenser_info = self.dispenser_data[cpid]
                        min_rate_btc = (
                            dispenser_info["min_satoshirate"] / 100000000.0 if dispenser_info["min_satoshirate"] else 0
                        )

                        # Check floor price
                        if not floor_price or floor_price == 0:
                            issues["missing_floor_price"].append(
                                {
                                    "cpid": cpid,
                                    "stamp": stamp_name,
                                    "dispenser_count": len(dispenser_info["dispensers"]),
                                    "min_rate_btc": min_rate_btc,
                                    "give_remaining": dispenser_info["total_give_remaining"],
                                }
                            )
                        elif abs(float(floor_price) - min_rate_btc) > 0.00000001:
                            issues["incorrect_floor_price"].append(
                                {
                                    "cpid": cpid,
                                    "stamp": stamp_name,
                                    "market_floor": float(floor_price),
                                    "actual_floor": min_rate_btc,
                                    "difference": abs(float(floor_price) - min_rate_btc),
                                }
                            )

                        # Check if floor price is stale
                        if last_updated and (datetime.now() - last_updated).days > 1:
                            issues["stale_floor_price"].append(
                                {
                                    "cpid": cpid,
                                    "stamp": stamp_name,
                                    "last_updated": last_updated,
                                    "days_old": (datetime.now() - last_updated).days,
                                }
                            )

                    # Check historical dispenses
                    if cpid in self.historical_dispenses:
                        recent_dispenses = [
                            d
                            for d in self.historical_dispenses[cpid]
                            if d.get("block_time", 0) > time.time() - 86400 * 30  # Last 30 days
                        ]

                        if recent_dispenses and (not sale_price or sale_price == 0):
                            last_dispense = max(recent_dispenses, key=lambda x: x.get("block_time", 0))
                            issues["missing_recent_sale"].append(
                                {
                                    "cpid": cpid,
                                    "stamp": stamp_name,
                                    "recent_dispenses": len(recent_dispenses),
                                    "last_dispense_block": last_dispense.get("block_index"),
                                    "volume_24h": volume_24h,
                                }
                            )

            return issues

        finally:
            db.close()

    def generate_report(self):
        """Generate comprehensive validation report."""
        print("\n" + "=" * 80)
        print("Dispenser Market Data Validation Report")
        print("=" * 80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Load stamps
        total_stamps = self.load_stamp_cpids()
        print(f"\nTotal Counterparty Stamps: {total_stamps:,}")

        # Fetch dispenser data
        print("\n🏪 Fetching Dispenser Data...")
        open_dispensers = self.fetch_open_dispensers()
        historical = self.fetch_historical_dispenses(sample_size=5000)

        print(f"\nDispenser Activity Summary:")
        print(f"  Stamps with open dispensers: {open_dispensers:,}")
        print(f"  Stamps with historical dispenses (sample): {historical:,}")
        print(
            f"  Total stamps with activity: {len(set(self.dispenser_data.keys()) | set(self.historical_dispenses.keys())):,}"
        )

        # Validate market data
        print("\n🔍 Validating Market Data...")
        issues = self.validate_market_data()

        # Report issues
        print("\n⚠️  Issues Found:")

        if issues["no_market_data"]:
            print(f"\n❌ No Market Data Record ({len(issues['no_market_data'])} stamps):")
            for item in issues["no_market_data"][:5]:
                status = []
                if item["has_open_dispensers"]:
                    status.append("open dispensers")
                if item["has_historical"]:
                    status.append("historical sales")
                print(f"  - {item['stamp']} ({item['cpid']}) - has {', '.join(status)}")
            if len(issues["no_market_data"]) > 5:
                print(f"  ... and {len(issues['no_market_data']) - 5} more")

        if issues["missing_floor_price"]:
            print(f"\n❌ Missing Floor Price ({len(issues['missing_floor_price'])} stamps with open dispensers):")
            for item in issues["missing_floor_price"][:5]:
                print(f"  - {item['stamp']} ({item['cpid']})")
                print(f"    • {item['dispenser_count']} dispensers, min rate: {item['min_rate_btc']:.8f} BTC")
                print(f"    • {item['give_remaining']:,} stamps available")
            if len(issues["missing_floor_price"]) > 5:
                print(f"  ... and {len(issues['missing_floor_price']) - 5} more")

        if issues["incorrect_floor_price"]:
            print(f"\n⚠️  Incorrect Floor Price ({len(issues['incorrect_floor_price'])} stamps):")
            for item in issues["incorrect_floor_price"][:5]:
                print(f"  - {item['stamp']} ({item['cpid']})")
                print(f"    • Market: {item['market_floor']:.8f} BTC")
                print(f"    • Actual: {item['actual_floor']:.8f} BTC")
                print(f"    • Diff: {item['difference']:.8f} BTC")
            if len(issues["incorrect_floor_price"]) > 5:
                print(f"  ... and {len(issues['incorrect_floor_price']) - 5} more")

        if issues["stale_floor_price"]:
            print(f"\n⏰ Stale Floor Price ({len(issues['stale_floor_price'])} stamps):")
            for item in issues["stale_floor_price"][:5]:
                print(f"  - {item['stamp']} ({item['cpid']}) - {item['days_old']} days old")
            if len(issues["stale_floor_price"]) > 5:
                print(f"  ... and {len(issues['stale_floor_price']) - 5} more")

        if issues["missing_recent_sale"]:
            print(f"\n💰 Missing Recent Sale Data ({len(issues['missing_recent_sale'])} stamps):")
            for item in issues["missing_recent_sale"][:5]:
                print(f"  - {item['stamp']} ({item['cpid']})")
                print(f"    • {item['recent_dispenses']} recent dispenses")
                print(f"    • Last at block {item['last_dispense_block']}")
            if len(issues["missing_recent_sale"]) > 5:
                print(f"  ... and {len(issues['missing_recent_sale']) - 5} more")

        # Summary
        print("\n📋 Summary:")
        total_issues = sum(len(items) for items in issues.values())

        if total_issues == 0:
            print("✅ All stamps with dispenser activity have proper market data!")
        else:
            print(f"❌ Found {total_issues:,} total issues:")
            for issue_type, items in issues.items():
                if items:
                    print(f"  - {issue_type.replace('_', ' ').title()}: {len(items):,}")

            print("\n🔧 Recommendations:")

            if issues["no_market_data"] or issues["missing_floor_price"]:
                print("  1. Run market data processor to create/update records:")
                print(
                    '     poetry run python -c "from src.index_core.stamp_market_processor import StampMarketProcessor; StampMarketProcessor().run()"'
                )

            if issues["missing_recent_sale"]:
                print("  2. Run sales history catchup to populate dispense sales:")
                print("     poetry run python tools/force_sales_history_catchup.py")

            if issues["incorrect_floor_price"] or issues["stale_floor_price"]:
                print("  3. Force refresh market data for affected stamps")
                print("     poetry run python tools/debug/fix_activity_updates.py")

        # Top stamps by activity
        print("\n📈 Top Stamps by Dispenser Activity:")
        top_by_dispensers = sorted(
            [(cpid, data) for cpid, data in self.dispenser_data.items()], key=lambda x: len(x[1]["dispensers"]), reverse=True
        )[:10]

        if top_by_dispensers:
            print("\nMost Active Dispensers:")
            db = self.db_manager.connect()
            try:
                for cpid, data in top_by_dispensers:
                    with db.cursor() as cursor:
                        cursor.execute("SELECT stamp FROM StampTableV4 WHERE cpid = %s", (cpid,))
                        stamp = cursor.fetchone()
                        stamp_name = stamp[0] if stamp else cpid

                        print(
                            f"  - {stamp_name}: {len(data['dispensers'])} dispensers, "
                            f"floor: {data['min_satoshirate']/100000000:.8f} BTC"
                        )
            finally:
                db.close()

        print("\n" + "=" * 80)


def main():
    """Main entry point."""
    validator = DispenserMarketDataValidator()
    validator.generate_report()


if __name__ == "__main__":
    main()
