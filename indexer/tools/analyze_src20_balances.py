#!/usr/bin/env python3
"""
Script to analyze SRC20 balance calculations for a specific address.
Compares database balances with calculated balances and API results.
"""

import json
import os
import sys
from collections import defaultdict
from decimal import ROUND_DOWN, Decimal
from typing import Dict, List, Tuple

import requests

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql as mysql

# Target address to analyze
TARGET_ADDRESS = "bc1qndwhntf80jv90kkkgvs67vp48hhpxeetrk9f5m"
# Comparison address for API test
COMPARISON_ADDRESS = "bc1qay74nc2djs2g5acqp72eyvlqp3ku7sj97jft8y"


def get_transactions_from_db(db, address: str) -> List[Dict]:
    """Get all SRC20 transactions for an address from the database."""
    cursor = db.cursor()

    query = """
    SELECT tick, block_index, tx_hash, creator, destination, amt, 
           creator_bal, destination_bal, op, status
    FROM SRC20Valid  
    WHERE (creator = %s OR destination = %s)
    ORDER BY block_index, tx_index
    """

    cursor.execute(query, (address, address))
    results = cursor.fetchall()

    transactions = []
    for row in results:
        tick, block_index, tx_hash, creator, destination, amt, creator_bal, dest_bal, op, status = row

        transactions.append(
            {
                "tick": tick,
                "block_index": block_index,
                "tx_hash": tx_hash,
                "creator": creator,
                "destination": destination,
                "amt": Decimal(str(amt)) if amt else Decimal("0"),
                "creator_bal": Decimal(str(creator_bal)) if creator_bal else None,
                "destination_bal": Decimal(str(dest_bal)) if dest_bal else None,
                "op": op,
                "status": status,
                "valid": 1 if not status else 0,
                "is_sender": creator == address,
                "is_receiver": destination == address,
            }
        )

    cursor.close()
    return transactions


def calculate_balances_from_transactions(transactions: List[Dict], address: str) -> Dict[str, Decimal]:
    """Calculate balances by processing transactions sequentially."""
    balances = defaultdict(Decimal)

    for tx in transactions:
        if tx["valid"] != 1:
            continue

        tick = tx["tick"]

        # Process based on operation type
        if tx["op"] == "MINT" and tx["is_receiver"]:
            balances[tick] += tx["amt"]
        elif tx["op"] == "TRANSFER":
            if tx["is_sender"]:
                balances[tick] -= tx["amt"]
            if tx["is_receiver"]:
                balances[tick] += tx["amt"]

    # Remove zero balances
    return {k: v for k, v in balances.items() if v > 0}


def get_current_balances_from_db(db, address: str) -> Dict[str, Decimal]:
    """Get current balances from the balances table."""
    cursor = db.cursor()

    query = """
    SELECT tick, amt
    FROM balances
    WHERE address = %s AND amt > 0
    """

    cursor.execute(query, (address,))
    results = cursor.fetchall()

    balances = {}
    for tick, amt in results:
        balances[tick] = Decimal(str(amt))

    cursor.close()
    return balances


def get_balances_from_api(address: str) -> Dict[str, Decimal]:
    """Get balances from the Stampchain API."""
    # The API returns balance for a specific token per call
    # For now, we'll return an empty dict as we'd need to know all ticks
    # to query the API for each one individually
    balances = {}

    # Get list of known ticks from a test query for 'stamp' token
    try:
        # Test with stamp token to verify API is working
        test_url = f"https://stampchain.io/api/v2/src20/balance/{address}/stamp"
        response = requests.get(test_url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if "data" in data:
                tick = data["data"].get("tick", "")
                amt = data["data"].get("amt", "0")
                if tick and amt:
                    balances[tick] = Decimal(str(amt))
                    print(f"   API test successful - found {tick} balance: {amt}")

        # For now, we'll just return what we found
        # In a full implementation, we'd need to query each tick individually
        return balances
    except Exception as e:
        print(f"Error fetching from API: {e}")
        return {}


def format_balance(balance: Decimal) -> str:
    """Format balance for display."""
    normalized = balance.normalize()
    if normalized == int(normalized):
        return str(int(normalized))
    else:
        return str(normalized)


def get_db_connection():
    """Get a direct database connection."""
    # Load environment variables
    if os.getcwd().endswith("/indexer"):
        sys.path.append(os.getcwd())
        dotenv_path = os.path.join(os.getcwd(), ".env")
    else:
        sys.path.append(os.path.join(os.getcwd(), "indexer"))
        dotenv_path = os.path.join(os.getcwd(), "indexer/.env")

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=dotenv_path, override=True)

    # Get connection parameters
    host = os.environ.get("RDS_HOSTNAME")
    user = os.environ.get("RDS_USER")
    password = os.environ.get("RDS_PASSWORD")
    database = "btc_stamps"

    return mysql.connect(host=host, user=user, password=password, database=database)


def main():
    """Main function to analyze balances."""
    print(f"Analyzing SRC20 balances for address: {TARGET_ADDRESS}")
    print("=" * 100)

    # Connect to database
    db = get_db_connection()

    try:
        # 1. Get all transactions
        print("\n1. Fetching all transactions from database...")
        transactions = get_transactions_from_db(db, TARGET_ADDRESS)
        print(f"   Found {len(transactions)} transactions")

        # 2. Calculate balances from transactions
        print("\n2. Calculating balances from transaction history...")
        calculated_balances = calculate_balances_from_transactions(transactions, TARGET_ADDRESS)

        # 3. Get current balances from balances table
        print("\n3. Fetching current balances from balances table...")
        db_balances = get_current_balances_from_db(db, TARGET_ADDRESS)

        # 4. Get balances from API
        print("\n4. Fetching balances from Stampchain API...")
        api_balances = get_balances_from_api(TARGET_ADDRESS)

        # 5. Compare results
        print("\n5. Balance Comparison:")
        print("=" * 100)

        # Get all unique ticks
        all_ticks = set(calculated_balances.keys()) | set(db_balances.keys()) | set(api_balances.keys())

        comparison_data = []
        mismatches = []

        for tick in sorted(all_ticks):
            calc_bal = calculated_balances.get(tick, Decimal("0"))
            db_bal = db_balances.get(tick, Decimal("0"))
            api_bal = api_balances.get(tick, Decimal("0"))

            # Check for mismatches
            if calc_bal != db_bal or calc_bal != api_bal or db_bal != api_bal:
                mismatches.append(tick)
                status = "MISMATCH"
            else:
                status = "OK"

            comparison_data.append([tick, format_balance(calc_bal), format_balance(db_bal), format_balance(api_bal), status])

        # Display comparison table
        headers = ["Tick", "Calculated", "DB Balance", "API Balance", "Status"]
        print(f"\n{'Tick':<10} {'Calculated':<15} {'DB Balance':<15} {'API Balance':<15} {'Status':<10}")
        print("-" * 70)
        for row in comparison_data:
            print(f"{row[0]:<10} {row[1]:<15} {row[2]:<15} {row[3]:<15} {row[4]:<10}")

        # 6. Show transaction details for mismatched ticks
        if mismatches:
            print(f"\n6. Transaction Details for Mismatched Ticks:")
            print("=" * 100)

            for tick in mismatches:
                print(f"\nTick: {tick}")
                print("-" * 80)

                tick_txs = [tx for tx in transactions if tx["tick"] == tick and tx["valid"] == 1]

                tx_data = []
                running_balance = Decimal("0")

                for tx in tick_txs:
                    # Calculate balance change
                    if tx["op"] == "MINT" and tx["is_receiver"]:
                        change = tx["amt"]
                        running_balance += change
                    elif tx["op"] == "TRANSFER":
                        if tx["is_sender"]:
                            change = -tx["amt"]
                            running_balance += change
                        elif tx["is_receiver"]:
                            change = tx["amt"]
                            running_balance += change
                        else:
                            continue
                    else:
                        continue

                    tx_data.append(
                        [
                            tx["block_index"],
                            tx["tx_hash"][:16] + "...",
                            tx["op"],
                            "SEND" if tx["is_sender"] else "RECEIVE",
                            format_balance(tx["amt"]),
                            format_balance(change) if "change" in locals() else "",
                            format_balance(running_balance),
                        ]
                    )

                tx_headers = ["Block", "TxHash", "Op", "Type", "Amount", "Change", "Balance"]
                print(f"{'Block':<10} {'TxHash':<20} {'Op':<10} {'Type':<10} {'Amount':<15} {'Change':<15} {'Balance':<15}")
                print("-" * 100)
                for tx_row in tx_data:
                    print(
                        f"{tx_row[0]:<10} {tx_row[1]:<20} {tx_row[2]:<10} {tx_row[3]:<10} {tx_row[4]:<15} {tx_row[5]:<15} {tx_row[6]:<15}"
                    )

        # 7. Test comparison address from API
        print(f"\n7. Testing comparison address: {COMPARISON_ADDRESS}")
        print("=" * 100)
        comp_api_balances = get_balances_from_api(COMPARISON_ADDRESS)
        if comp_api_balances:
            print(f"Found {len(comp_api_balances)} tokens for comparison address")
            for tick, balance in sorted(comp_api_balances.items())[:5]:  # Show first 5
                print(f"  {tick}: {format_balance(balance)}")

    finally:
        db.close()

    print("\nAnalysis complete.")


if __name__ == "__main__":
    main()
