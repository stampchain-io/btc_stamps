#!/usr/bin/env python3
"""
Manual Market Data Population Script

This script manually triggers market data population for stamps and SRC-20 tokens.
It can be used to populate data when the background scheduler is not running.
"""

import os
import sys
import logging
import time
from datetime import datetime

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from index_core.database_manager import DatabaseManager
from index_core.market_data_jobs import MarketDataJobScheduler
from index_core.market_data_service import market_data_service
from index_core.src20_worker import SRC20Worker
from index_core.stamp_worker import StampWorker
import config

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def check_api_keys():
    """Check if required API keys are set."""
    missing_keys = []

    if not os.getenv("OPENSTAMP_API_KEY"):
        missing_keys.append("OPENSTAMP_API_KEY")

    if missing_keys:
        print("\n❌ ERROR: Missing required API keys:")
        for key in missing_keys:
            print(f"  - {key}")
        print("\nPlease set these environment variables before running this script.")
        return False

    return True


def populate_stamp_market_data(limit=100):
    """Manually populate stamp market data."""
    print(f"\n📊 Populating stamp market data (limit: {limit})...")

    db_manager = DatabaseManager()
    db = db_manager.connect()

    try:
        # Get stamps that need updates
        with db.cursor() as cursor:
            # Get stamps that have never been updated or are stale
            cursor.execute(
                f"""
                SELECT DISTINCT s.cpid
                FROM StampTableV4 s
                LEFT JOIN stamp_market_data smd ON s.cpid = smd.cpid
                WHERE s.cpid IS NOT NULL
                  AND s.cpid != ''
                  AND (smd.last_updated IS NULL 
                       OR smd.last_updated < DATE_SUB(NOW(), INTERVAL 1 DAY))
                ORDER BY s.stamp DESC
                LIMIT %s
            """,
                (limit,),
            )

            cpids = [row[0] for row in cursor.fetchall()]

        print(f"Found {len(cpids)} stamps to update")

        if not cpids:
            print("No stamps need updates")
            return

        # Create worker and process stamps
        stamp_worker = StampWorker()
        success_count = 0
        error_count = 0

        for i, cpid in enumerate(cpids, 1):
            try:
                print(f"Processing {i}/{len(cpids)}: {cpid}", end="... ")

                # Get market data for this stamp
                market_data = stamp_worker.process_stamp_market_data(cpid)

                if market_data:
                    # Extract holder cache data if present
                    holder_cache_data = market_data.pop("_holder_cache_data", None)

                    # Update market data
                    market_data_service.update_stamp_market_data(cpid, market_data)
                    success_count += 1
                    print("✅")

                    # Populate holder cache if available
                    if holder_cache_data:
                        _populate_holder_cache(db, cpid, holder_cache_data)
                else:
                    error_count += 1
                    print("❌ No data")

            except Exception as e:
                error_count += 1
                print(f"❌ Error: {e}")
                logger.error(f"Error processing stamp {cpid}: {e}")

            # Rate limiting
            if i % 10 == 0:
                time.sleep(1)  # Brief pause every 10 stamps

        print(f"\n✅ Stamp updates complete: {success_count} successful, {error_count} errors")

    finally:
        db.close()


def populate_src20_market_data():
    """Manually populate SRC-20 market data."""
    print("\n📊 Populating SRC-20 market data...")

    if not os.getenv("OPENSTAMP_API_KEY"):
        print("❌ OpenStamp API key not set - skipping SRC-20 updates")
        return

    db_manager = DatabaseManager()
    db = db_manager.connect()

    try:
        # Get all SRC-20 tokens from database
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT tick
                FROM SRC20Valid
                WHERE tick IS NOT NULL
                AND tick != ''
                ORDER BY tick
            """
            )

            database_tokens = {row[0] for row in cursor.fetchall()}

        print(f"Found {len(database_tokens)} SRC-20 tokens in database")

        # Create worker and fetch OpenStamp data
        src20_worker = SRC20Worker()

        print("Fetching data from OpenStamp...")
        openstamp_tokens = src20_worker.fetch_all_openstamp_data()

        if not openstamp_tokens:
            print("❌ No data received from OpenStamp")
            return

        print(f"Received data for {len(openstamp_tokens)} tokens from OpenStamp")

        # Process tokens
        success_count = 0
        error_count = 0

        for token_data in openstamp_tokens:
            tick = token_data.get("name", "").upper()

            # Only process if token exists in our database and is valid SRC-20
            if tick in database_tokens and len(tick) <= 5:
                try:
                    # Transform and store the market data
                    market_data = src20_worker.transform_openstamp_data(token_data)
                    if market_data:
                        market_data_service.update_src20_market_data(tick, market_data)
                        success_count += 1

                        # Store source tracking data
                        source_data = {"openstamp": market_data}
                        src20_worker._store_source_data(tick, source_data)
                    else:
                        error_count += 1

                except Exception as e:
                    error_count += 1
                    logger.error(f"Error processing token {tick}: {e}")

        # Also update STAMP token from KuCoin if available
        try:
            print("\nFetching STAMP token data from KuCoin...")
            stamp_data = src20_worker.process_src20_market_data("STAMP")
            if stamp_data:
                market_data_service.update_src20_market_data("STAMP", stamp_data)
                print("✅ Updated STAMP token from KuCoin")
            else:
                print("❌ No STAMP data from KuCoin")
        except Exception as e:
            print(f"❌ Error updating STAMP from KuCoin: {e}")

        print(f"\n✅ SRC-20 updates complete: {success_count} successful, {error_count} errors")

    finally:
        db.close()


def _populate_holder_cache(db, cpid, holder_data):
    """Helper to populate holder cache."""
    try:
        if not holder_data:
            return

        # Sort holders by quantity
        sorted_holders = sorted(holder_data, key=lambda x: x["quantity"], reverse=True)
        total_supply = sum(holder["quantity"] for holder in holder_data)

        with db.cursor() as cursor:
            # Clear existing cache
            cursor.execute("DELETE FROM stamp_holder_cache WHERE cpid = %s", (cpid,))

            # Insert new holder records
            insert_values = []
            for rank, holder in enumerate(sorted_holders, 1):
                percentage = (holder["quantity"] / total_supply * 100) if total_supply > 0 else 0
                insert_values.append((cpid, holder["address"], holder["quantity"], percentage, rank, "counterparty", None))

            if insert_values:
                cursor.executemany(
                    """
                    INSERT INTO stamp_holder_cache
                    (cpid, address, quantity, percentage, rank_position, balance_source, last_tx_block)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                    insert_values,
                )

        # Commit if not in autocommit mode
        try:
            db.commit()
        except:
            pass  # Autocommit mode

    except Exception as e:
        logger.error(f"Error populating holder cache for {cpid}: {e}")


def show_sample_data():
    """Show sample data after population."""
    print("\n📊 Sample market data after population:")

    db_manager = DatabaseManager()
    db = db_manager.connect()

    try:
        with db.cursor() as cursor:
            # Sample stamp data
            print("\n=== STAMP MARKET DATA (Top 5 by volume) ===")
            cursor.execute(
                """
                SELECT cpid, floor_price_btc, holder_count, 
                       volume_24h_btc, price_source, 
                       data_quality_score, last_updated
                FROM stamp_market_data
                WHERE volume_24h_btc > 0
                ORDER BY volume_24h_btc DESC
                LIMIT 5
            """
            )

            results = cursor.fetchall()
            if results:
                for row in results:
                    cpid, floor, holders, vol, source, quality, updated = row
                    print(f"\n{cpid}:")
                    print(f"  Floor: {floor} BTC, Holders: {holders}")
                    print(f"  24h Vol: {vol} BTC, Source: {source}")
                    print(f"  Quality: {quality}, Updated: {updated}")
            else:
                print("No stamps with volume data found")

            # Sample SRC-20 data
            print("\n=== SRC-20 MARKET DATA (Top 5 by market cap) ===")
            cursor.execute(
                """
                SELECT tick, price_btc, market_cap_btc, 
                       volume_24h_btc, primary_exchange,
                       holder_count, last_updated
                FROM src20_market_data
                WHERE market_cap_btc > 0
                ORDER BY market_cap_btc DESC
                LIMIT 5
            """
            )

            results = cursor.fetchall()
            if results:
                for row in results:
                    tick, price, mcap, vol, exchange, holders, updated = row
                    print(f"\n{tick}:")
                    print(f"  Price: {price} BTC, MCap: {mcap} BTC")
                    print(f"  24h Vol: {vol} BTC, Exchange: {exchange}")
                    print(f"  Holders: {holders}, Updated: {updated}")
            else:
                print("No SRC-20 tokens with market cap data found")

    finally:
        db.close()


def main():
    """Main function."""
    print("=" * 80)
    print("BITCOIN STAMPS MARKET DATA POPULATION TOOL")
    print("=" * 80)
    print(f"Timestamp: {datetime.now()}")

    # Check API keys
    if not check_api_keys():
        return 1

    # Check if scheduler is enabled
    if config.ENABLE_MARKET_DATA_SCHEDULER:
        print("\n⚠️  WARNING: Market data scheduler is ENABLED in config")
        print("This script will populate data manually, but the scheduler may also be running.")
        response = input("\nContinue anyway? (y/N): ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    try:
        # Populate stamp data
        populate_stamp_market_data(limit=100)  # Start with 100 stamps

        # Populate SRC-20 data
        populate_src20_market_data()

        # Show sample results
        show_sample_data()

        print("\n✅ Market data population complete!")
        print("\nTo populate more stamps, run:")
        print("  poetry run python tools/debug/populate_market_data.py --stamps 1000")

    except Exception as e:
        logger.error(f"Error during population: {e}")
        print(f"\n❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    # Simple argument parsing
    import sys

    if len(sys.argv) > 2 and sys.argv[1] == "--stamps":
        try:
            limit = int(sys.argv[2])
            populate_stamp_market_data(limit=limit)
            show_sample_data()
        except ValueError:
            print("Invalid stamp limit. Usage: --stamps <number>")
            sys.exit(1)
    else:
        sys.exit(main())
