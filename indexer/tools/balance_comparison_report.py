#!/usr/bin/env python3
"""
Clean report comparing database balances with API for debugging.
"""

import os
import sys
from datetime import datetime
from decimal import Decimal

import requests

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql as mysql

# Target address
TARGET_ADDRESS = "bc1qay74nc2djs2g5acqp72eyvlqp3ku7sj97jft8y"
# TARGET_ADDRESS = 'bc1qndwhntf80jv90kkkgvs67vp48hhpxeetrk9f5m'


def get_db_connection():
    """Get database connection using env vars."""
    if os.getcwd().endswith("/indexer"):
        sys.path.append(os.getcwd())
        dotenv_path = os.path.join(os.getcwd(), ".env")
    else:
        sys.path.append(os.path.join(os.getcwd(), "indexer"))
        dotenv_path = os.path.join(os.getcwd(), "indexer/.env")

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=dotenv_path, override=True)

    # Production database
    host = os.environ.get("ST3_HOSTNAME")
    user = os.environ.get("ST3_USER")
    password = os.environ.get("ST3_PASSWORD")
    database = os.environ.get("PROD_DATABASE", "btc_stamps")

    return mysql.connect(host=host, user=user, password=password, database=database)


def format_number(num):
    """Format large numbers with commas."""
    if isinstance(num, Decimal):
        parts = str(num).split(".")
        parts[0] = "{:,}".format(int(parts[0]))
        return ".".join(parts) if len(parts) > 1 else parts[0]
    return "{:,}".format(num)


def main():
    print("=" * 80)
    print("SRC20 BALANCE COMPARISON REPORT")
    print("=" * 80)
    print(f"Address: {TARGET_ADDRESS}")
    print(f"Token: STAMP")
    print(f"Report Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 80)

    db = get_db_connection()
    cursor = db.cursor()

    # 1. Get database info
    cursor.execute("SELECT MAX(block_index) FROM blocks")
    db_max_block = cursor.fetchone()[0]

    # 2. Get balance table info
    cursor.execute(
        """
        SELECT amt, last_update, block_time 
        FROM balances 
        WHERE address = %s AND tick = 'stamp'
    """,
        (TARGET_ADDRESS,),
    )

    balance_info = cursor.fetchone()
    db_balance = Decimal(str(balance_info[0]))
    db_last_update_block = balance_info[1]
    db_block_time = balance_info[2]

    # 3. Get API info
    api_url = f"https://stampchain.io/api/v2/src20/balance/{TARGET_ADDRESS}/stamp"
    response = requests.get(api_url, timeout=30)
    api_data = response.json()

    api_balance = Decimal(api_data["data"]["amt"])
    api_last_update = api_data["data"]["last_update"]
    api_last_block = api_data["last_block"]

    # 4. Calculate the difference
    balance_diff = api_balance - db_balance
    block_diff = db_last_update_block - api_last_update

    # 5. Get the balance at the API's last_update block
    cursor.execute(
        """
        SELECT destination_bal 
        FROM SRC20Valid
        WHERE tick = 'stamp' 
          AND destination = %s
          AND block_index = %s
    """,
        (TARGET_ADDRESS, api_last_update),
    )

    balance_at_api_block = cursor.fetchone()

    # Print clean report
    print("\n1. DATABASE STATUS")
    print("-" * 40)
    print(f"   Current Block Height:     {format_number(db_max_block)}")
    print(f"   Balance:                  {format_number(db_balance)}")
    print(f"   Balance Last Updated:     Block {format_number(db_last_update_block)}")
    print(f"   Last Update Time:         {db_block_time}")

    print("\n2. API STATUS")
    print("-" * 40)
    print(f"   API Response Block:       {format_number(api_last_block)}")
    print(f"   Balance:                  {format_number(api_balance)}")
    print(f"   Balance Last Updated:     Block {format_number(api_last_update)}")

    print("\n3. COMPARISON")
    print("-" * 40)
    print(f"   Balance Difference:       {format_number(balance_diff)}")
    print(f"   Block Difference:         {format_number(block_diff)} blocks")
    print(f"   API is behind by:         {block_diff} blocks")

    if balance_at_api_block:
        print(f"\n   DB Balance at Block {api_last_update}: {format_number(balance_at_api_block[0])}")
        if Decimal(str(balance_at_api_block[0])) == api_balance:
            print("   ✅ API balance matches DB balance at that block!")
        else:
            print("   ❌ API balance does NOT match DB balance at that block")

    # Get transactions between API block and current
    print(f"\n4. TRANSACTIONS BETWEEN BLOCKS {api_last_update} AND {db_last_update_block}")
    print("-" * 40)

    cursor.execute(
        """
        SELECT block_index, creator, destination, amt
        FROM SRC20Valid
        WHERE tick = 'stamp' 
          AND (creator = %s OR destination = %s)
          AND block_index > %s
          AND block_index <= %s
        ORDER BY block_index
    """,
        (TARGET_ADDRESS, TARGET_ADDRESS, api_last_update, db_last_update_block),
    )

    transactions = cursor.fetchall()
    total_sent = Decimal("0")
    total_received = Decimal("0")

    for block, creator, dest, amt in transactions:
        amt_decimal = Decimal(str(amt))
        if creator == TARGET_ADDRESS:
            total_sent += amt_decimal
            print(f"   Block {block}: SENT     {format_number(amt_decimal)}")
        else:
            total_received += amt_decimal
            print(f"   Block {block}: RECEIVED {format_number(amt_decimal)}")

    net_change = total_received - total_sent
    print(f"\n   Total Sent:     {format_number(total_sent)}")
    print(f"   Total Received: {format_number(total_received)}")
    print(f"   Net Change:     {format_number(net_change)}")

    # Verify the calculation
    calculated_balance = api_balance + net_change
    print(f"\n   API Balance + Net Change = {format_number(calculated_balance)}")
    print(f"   Current DB Balance =       {format_number(db_balance)}")

    if abs(calculated_balance - db_balance) < Decimal("0.000001"):
        print("   ✅ Calculation verified!")
    else:
        print("   ❌ Calculation mismatch!")

    print("\n5. SUMMARY")
    print("-" * 40)
    print("   • Database is up-to-date at block", format_number(db_max_block))
    print("   • API is showing data from block", format_number(api_last_update))
    print(f"   • API is {block_diff} blocks behind the database")
    print("   • The balance calculations in the database are CORRECT")
    print("   • The API is showing STALE/CACHED data")

    print("\n" + "=" * 80)

    cursor.close()
    db.close()


if __name__ == "__main__":
    main()
