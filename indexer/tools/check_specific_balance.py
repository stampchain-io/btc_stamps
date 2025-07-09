#!/usr/bin/env python3
"""
Script to check SRC20 balance calculations for a specific address.
This runs the exact query provided and compares calculations.
"""

import os
import sys
from collections import defaultdict
from decimal import Decimal

import requests

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql as mysql

# Target address
TARGET_ADDRESS = "bc1qndwhntf80jv90kkkgvs67vp48hhpxeetrk9f5m"


def get_db_connection(use_production=True):
    """Get database connection using env vars."""
    if os.getcwd().endswith("/indexer"):
        sys.path.append(os.getcwd())
        dotenv_path = os.path.join(os.getcwd(), ".env")
    else:
        sys.path.append(os.path.join(os.getcwd(), "indexer"))
        dotenv_path = os.path.join(os.getcwd(), "indexer/.env")

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=dotenv_path, override=True)

    if use_production:
        # Production database
        host = os.environ.get("ST3_HOSTNAME")
        user = os.environ.get("ST3_USER")
        password = os.environ.get("ST3_PASSWORD")
        database = os.environ.get("PROD_DATABASE", "btc_stamps")
        print(f"Connecting to PRODUCTION database at {host}")
    else:
        # Local/dev database
        host = os.environ.get("RDS_HOSTNAME")
        user = os.environ.get("RDS_USER")
        password = os.environ.get("RDS_PASSWORD")
        database = "btc_stamps"
        print(f"Connecting to LOCAL database at {host}")

    return mysql.connect(host=host, user=user, password=password, database=database)


def main():
    print(f"Checking SRC20 balances for: {TARGET_ADDRESS}")
    print("=" * 80)

    db = get_db_connection()
    cursor = db.cursor()

    # Run the exact query provided
    query = """
    SELECT tick, block_index, tx_hash, creator, destination, amt, creator_bal, destination_bal  
    FROM SRC20Valid  
    WHERE creator = %s OR destination = %s
    ORDER BY block_index
    """

    cursor.execute(query, (TARGET_ADDRESS, TARGET_ADDRESS))
    results = cursor.fetchall()

    print(f"\n1. Found {len(results)} transactions")

    # Calculate balances manually
    manual_balances = defaultdict(Decimal)
    tick_transactions = defaultdict(list)

    for row in results:
        tick, block_index, tx_hash, creator, destination, amt, creator_bal, dest_bal = row
        amt = Decimal(str(amt)) if amt else Decimal("0")

        # Store transaction for detailed analysis
        tick_transactions[tick].append(
            {
                "block": block_index,
                "tx_hash": tx_hash,
                "creator": creator,
                "destination": destination,
                "amt": amt,
                "creator_bal": creator_bal,
                "dest_bal": dest_bal,
                "is_send": creator == TARGET_ADDRESS,
                "is_receive": destination == TARGET_ADDRESS,
            }
        )

        # Calculate balance changes
        if creator == TARGET_ADDRESS:
            manual_balances[tick] -= amt
        if destination == TARGET_ADDRESS:
            manual_balances[tick] += amt

    # Get current balances from the database
    cursor.execute(
        """
        SELECT tick, amt 
        FROM balances 
        WHERE address = %s AND amt > 0
    """,
        (TARGET_ADDRESS,),
    )

    db_balances = {}
    for tick, amt in cursor.fetchall():
        db_balances[tick] = Decimal(str(amt))

    # Compare balances
    print(f"\n2. Balance Comparison:")
    print(f"{'Tick':<10} {'Manual Calc':<25} {'DB Balance':<25} {'Match':<10}")
    print("-" * 80)

    all_ticks = set(manual_balances.keys()) | set(db_balances.keys())
    mismatches = []

    for tick in sorted(all_ticks):
        manual = manual_balances.get(tick, Decimal("0"))
        db_bal = db_balances.get(tick, Decimal("0"))

        # Clean up zero balances
        if manual == 0:
            manual = Decimal("0")
        if manual < 0:  # Should not happen in valid transactions
            print(f"WARNING: Negative balance for {tick}: {manual}")

        match = "YES" if manual == db_bal else "NO"
        if match == "NO":
            mismatches.append(tick)

        print(f"{tick:<10} {str(manual):<25} {str(db_bal):<25} {match:<10}")

    # For mismatches, show transaction details
    if mismatches:
        print(f"\n3. Transaction Details for Mismatched Tokens:")
        print("=" * 80)

        for tick in mismatches[:3]:  # Show first 3 mismatches
            print(f"\nTick: {tick}")
            print("-" * 60)

            transactions = tick_transactions[tick]
            running_balance = Decimal("0")

            print(f"{'Block':<10} {'TX Hash':<20} {'Type':<10} {'Amount':<20} {'Running Bal':<20}")
            print("-" * 60)

            for tx in transactions[:20]:  # Show first 20 transactions
                if tx["is_send"]:
                    tx_type = "SEND"
                    running_balance -= tx["amt"]
                elif tx["is_receive"]:
                    tx_type = "RECEIVE"
                    running_balance += tx["amt"]
                else:
                    continue

                print(
                    f"{tx['block']:<10} {tx['tx_hash'][:16]+'...':<20} {tx_type:<10} {str(tx['amt']):<20} {str(running_balance):<20}"
                )

    # Check specific token balance from API
    print(f"\n4. Checking 'stamp' token balance from API...")
    try:
        api_url = f"https://stampchain.io/api/v2/src20/balance/{TARGET_ADDRESS}/stamp"
        response = requests.get(api_url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if "data" in data:
                api_amt = data["data"].get("amt", "0")
                api_balance = Decimal(str(api_amt))
                manual_stamp = manual_balances.get("stamp", Decimal("0"))
                db_stamp = db_balances.get("stamp", Decimal("0"))

                print(f"\n   Manual calculation: {manual_stamp}")
                print(f"   Database balance:   {db_stamp}")
                print(f"   API balance:        {api_balance}")

                if manual_stamp == db_stamp == api_balance:
                    print(f"   ✓ All three sources match!")
                else:
                    print(f"   ✗ Mismatch detected!")
    except Exception as e:
        print(f"   Error checking API: {e}")

    # Test the comparison address
    print(f"\n5. Testing comparison address API...")
    comparison_address = "bc1qay74nc2djs2g5acqp72eyvlqp3ku7sj97jft8y"
    try:
        api_url = f"https://stampchain.io/api/v2/src20/balance/{comparison_address}/stamp"
        response = requests.get(api_url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if "data" in data:
                api_amt = data["data"].get("amt", "0")
                print(f"   Address: {comparison_address}")
                print(f"   Stamp balance: {api_amt}")
        else:
            print(f"   API returned status: {response.status_code}")
    except Exception as e:
        print(f"   Error: {e}")

    cursor.close()
    db.close()

    print("\nAnalysis complete.")


if __name__ == "__main__":
    main()
