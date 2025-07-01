#!/usr/bin/env python3
"""
Quick diagnostic script to check market data population in production
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

# Production database connection using ST3_ variables
prod_host = os.environ.get("ST3_HOSTNAME")
prod_user = os.environ.get("ST3_USER")
prod_password = os.environ.get("ST3_PASSWORD")
prod_database = os.environ.get("PROD_DATABASE", "btc_stamps")

print(f"Connecting to production database: {prod_host}/{prod_database}")

conn = pymysql.connect(host=prod_host, user=prod_user, password=prod_password, database=prod_database)

cursor = conn.cursor()

try:
    # Check if tables exist
    print("\n=== Checking Market Data Tables ===")

    tables = ["stamp_market_data", "src20_market_data", "market_data_sources", "stamp_holder_cache", "collection_market_data"]

    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"{table}: {count} records")

    # Check stamp_market_data population
    print("\n=== Stamp Market Data Analysis ===")
    cursor.execute(
        """
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN price_source IS NULL THEN 1 END) as null_price_source,
            COUNT(CASE WHEN volume_sources IS NULL OR volume_sources = '{}' THEN 1 END) as empty_volume_sources,
            COUNT(CASE WHEN volume_24h_btc > 0 THEN 1 END) as has_24h_volume,
            COUNT(CASE WHEN holder_count > 0 THEN 1 END) as has_holders
        FROM stamp_market_data
    """
    )

    result = cursor.fetchone()
    print(f"Total stamps: {result[0]}")
    print(f"NULL price_source: {result[1]} ({result[1]/result[0]*100:.1f}%)" if result[0] > 0 else "No data")
    print(f"Empty volume_sources: {result[2]} ({result[2]/result[0]*100:.1f}%)" if result[0] > 0 else "No data")
    print(f"Has 24h volume: {result[3]} ({result[3]/result[0]*100:.1f}%)" if result[0] > 0 else "No data")
    print(f"Has holder count: {result[4]} ({result[4]/result[0]*100:.1f}%)" if result[0] > 0 else "No data")

    # Check SRC-20 market data
    print("\n=== SRC-20 Market Data Analysis ===")
    cursor.execute(
        """
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN price_btc IS NOT NULL THEN 1 END) as has_price,
            COUNT(CASE WHEN primary_exchange IS NOT NULL THEN 1 END) as has_exchange,
            COUNT(CASE WHEN volume_24h_btc > 0 THEN 1 END) as has_volume
        FROM src20_market_data
    """
    )

    result = cursor.fetchone()
    print(f"Total SRC-20 tokens: {result[0]}")
    if result[0] > 0:
        print(f"Has price: {result[1]} ({result[1]/result[0]*100:.1f}%)")
        print(f"Has exchange: {result[2]} ({result[2]/result[0]*100:.1f}%)")
        print(f"Has volume: {result[3]} ({result[3]/result[0]*100:.1f}%)")

    # Check specific high-volume tokens
    print("\n=== High-Volume Token Check ===")
    for tick in ["STAMP", "KEVIN", "PEPE"]:
        cursor.execute(
            """
            SELECT tick, price_btc, volume_24h_btc, primary_exchange, last_updated
            FROM src20_market_data
            WHERE tick = %s
        """,
            (tick,),
        )

        result = cursor.fetchone()
        if result:
            print(f"\n{tick}:")
            print(f"  Price BTC: {result[1]}")
            print(f"  24h Volume: {result[2]}")
            print(f"  Exchange: {result[3]}")
            print(f"  Last Update: {result[4]}")
        else:
            print(f"\n{tick}: NOT FOUND in src20_market_data")

    # Check environment configuration
    print("\n=== Environment Configuration ===")
    scheduler_enabled = os.environ.get("ENABLE_MARKET_DATA_SCHEDULER", "false")
    openstamp_key = os.environ.get("OPENSTAMP_API_KEY", "")
    kucoin_key = os.environ.get("KUCOIN_API_KEY", "")

    print(f"ENABLE_MARKET_DATA_SCHEDULER: {scheduler_enabled}")
    print(f"OPENSTAMP_API_KEY: {'SET' if openstamp_key else 'NOT SET'}")
    print(f"KUCOIN_API_KEY: {'SET' if kucoin_key else 'NOT SET'}")

    print("\n=== Recommendations ===")
    if scheduler_enabled.lower() != "true":
        print("❌ Market data scheduler is DISABLED. Set ENABLE_MARKET_DATA_SCHEDULER=true")
    if not openstamp_key:
        print("❌ OpenStamp API key is NOT SET. Required for SRC-20 token data")
    if not kucoin_key:
        print("⚠️  KuCoin API key is NOT SET. Optional for STAMP token on KuCoin")

    if result[0] == 0:  # No SRC-20 data
        print("❌ No SRC-20 market data found. The background jobs may not be running.")
        print("   Run: poetry run python tools/debug/populate_market_data.py")

finally:
    cursor.close()
    conn.close()
