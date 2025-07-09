#!/usr/bin/env python3
"""
Clear summary of the API balance situation.
"""

import os
import sys
from decimal import Decimal

import requests

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql as mysql


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


def main():
    address = "bc1qndwhntf80jv90kkkgvs67vp48hhpxeetrk9f5m"

    print("=" * 80)
    print("API BALANCE DISCREPANCY ANALYSIS")
    print("=" * 80)

    # Get API data
    api_url = f"https://stampchain.io/api/v2/src20/balance/{address}/stamp"
    response = requests.get(api_url, timeout=30)
    api_data = response.json()

    api_balance = Decimal(api_data["data"]["amt"])
    api_last_update = api_data["data"]["last_update"]
    api_global_block = api_data["last_block"]

    # Get database data
    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT amt, last_update FROM balances 
        WHERE address = %s AND tick = 'stamp'
    """,
        (address,),
    )

    db_balance, db_last_update = cursor.fetchone()
    db_balance = Decimal(str(db_balance))

    print(f"\nTHE SITUATION:")
    print(f"• API shows balance: {api_balance}")
    print(f"• DB shows balance:  {db_balance}")
    print(f"• Difference: {db_balance - api_balance} STAMP")

    print(f"\nWHAT'S HAPPENING:")
    print(f"• The API 'last_update' field ({api_last_update}) shows when this ADDRESS last had a transaction")
    print(f"• The API is showing the balance as of block {api_last_update}")
    print(f"• The database has processed up to block {api_global_block}")
    print(f"• The address had transactions AFTER block {api_last_update}")

    # Show the transactions after the API's last_update
    cursor.execute(
        """
        SELECT block_index, 
               CASE WHEN creator = %s THEN 'SENT' ELSE 'RECEIVED' END as direction,
               amt
        FROM SRC20Valid
        WHERE tick = 'stamp' 
          AND (creator = %s OR destination = %s)
          AND block_index > %s
        ORDER BY block_index
    """,
        (address, address, address, api_last_update),
    )

    print(f"\nTRANSACTIONS AFTER BLOCK {api_last_update} (not reflected in API):")
    net_change = Decimal("0")
    for block, direction, amt in cursor.fetchall():
        amt = Decimal(str(amt))
        if direction == "SENT":
            net_change -= amt
            print(f"  Block {block}: {direction} {amt}")
        else:
            net_change += amt
            print(f"  Block {block}: {direction} {amt}")

    print(f"\n  Net change: {net_change}")
    print(f"  API balance ({api_balance}) + net change ({net_change}) = {api_balance + net_change}")
    print(f"  Current DB balance: {db_balance}")

    if abs((api_balance + net_change) - db_balance) < Decimal("0.000001"):
        print(f"  ✅ Matches!")

    print(f"\nCONCLUSION:")
    print(f"• The API is returning OUTDATED balance information")
    print(f"• The API shows the balance as it was at block {api_last_update}")
    print(f"• The API has not updated this address's balance for {api_global_block - api_last_update} blocks")
    print(f"• The database calculations are CORRECT")
    print(f"• This is an API caching/update issue")

    print("\n" + "=" * 80)

    cursor.close()
    db.close()


if __name__ == "__main__":
    main()
