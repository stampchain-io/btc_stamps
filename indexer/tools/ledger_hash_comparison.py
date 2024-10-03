import os
import sys
from collections import defaultdict
from decimal import Decimal

# Add the parent directory to the Python path
if os.getcwd().endswith("/indexer"):
    sys.path.append(os.getcwd())
    dotenv_path = os.path.join(os.getcwd(), ".env")
else:
    sys.path.append(os.path.join(os.getcwd(), "indexer"))
    dotenv_path = os.path.join(os.getcwd(), "indexer/.env")

import pymysql as mysql
from dotenv import load_dotenv
from tqdm import tqdm

from index_core.src20 import fetch_api_ledger_data

# from index_core.config import SRC20_VALID_TABLE
SRC20_VALID_TABLE = "SRC20Valid"

load_dotenv(dotenv_path=dotenv_path, override=True)

START_BLOCK = 820197  # 793068


def get_db_connection():
    return mysql.connect(
        host=os.environ.get("RDS_HOSTNAME"),
        user=os.environ.get("RDS_USER"),
        password=os.environ.get("RDS_PASSWORD"),
        database="btc_stamps",
        charset="utf8mb4",
        cursorclass=mysql.cursors.DictCursor,
    )


def get_all_local_ledger_hashes(cursor, start_block, end_block):
    cursor.execute("SELECT block_index, ledger_hash FROM blocks WHERE block_index BETWEEN %s AND %s", (start_block, end_block))
    return {row["block_index"]: row["ledger_hash"] for row in cursor.fetchall()}


def calculate_balances(cursor, block_index):
    query = f"""
    SELECT op, creator, destination, tick, tick_hash, amt
    FROM {SRC20_VALID_TABLE}
    WHERE block_index <= %s AND (op = 'TRANSFER' OR op = 'MINT') AND amt > 0
    ORDER BY block_index, tx_index
    """
    cursor.execute(query, (block_index,))
    src20_valid_list = cursor.fetchall()

    balances = defaultdict(lambda: defaultdict(Decimal))
    for op, creator, destination, tick, tick_hash, amt in src20_valid_list:
        amt = Decimal(amt)
        if op == "MINT":
            balances[tick][destination] += amt
        elif op == "TRANSFER":
            balances[tick][creator] -= amt
            balances[tick][destination] += amt

    return balances


def get_block_changes(cursor, block_index):
    query = f"""
    SELECT op, creator, destination, tick, tick_hash, amt
    FROM {SRC20_VALID_TABLE}
    WHERE block_index = %s AND (op = 'TRANSFER' OR op = 'MINT') AND amt > 0
    ORDER BY tx_index
    """
    cursor.execute(query, (block_index,))
    return cursor.fetchall()


def generate_valid_src20_str(balances, changes):
    updated_balances = defaultdict(lambda: defaultdict(Decimal))
    for op, creator, destination, tick, tick_hash, amt in changes:
        amt = Decimal(amt)
        if op == "MINT":
            updated_balances[tick][destination] = balances[tick][destination] + amt
        elif op == "TRANSFER":
            updated_balances[tick][creator] = balances[tick][creator] - amt
            updated_balances[tick][destination] = balances[tick][destination] + amt

    valid_src20_list = [
        f"{tick},{address},{balance}"
        for tick in sorted(updated_balances.keys())
        for address in sorted(updated_balances[tick].keys())
        for balance in [updated_balances[tick][address]]
        if balance > 0
    ]
    return ";".join(valid_src20_list)


def compare_balances(local_balances, api_balances):
    differences = []
    all_addresses = set()
    for tick_balances in local_balances.values():
        all_addresses.update(tick_balances.keys())
    for tick_balances in api_balances.values():
        all_addresses.update(tick_balances.keys())

    for address in sorted(all_addresses):
        address_differences = []
        for tick in sorted(set(local_balances.keys()) | set(api_balances.keys())):
            local_balance = local_balances.get(tick, {}).get(address, Decimal("0"))
            api_balance = api_balances.get(tick, {}).get(address, Decimal("0"))
            if local_balance != api_balance:
                address_differences.append((tick, local_balance, api_balance))
        if address_differences:
            differences.append((address, address_differences))

    return differences


def print_balance_differences(differences):
    print("\nBalance Differences:")
    print("--------------------")
    for address, address_differences in differences:
        print(f"\nAddress: {address}")
        print("  {:<10} {:<20} {:<20} {:<20}".format("Tick", "Local Balance", "API Balance", "Difference"))
        print("  " + "-" * 70)
        for tick, local_balance, api_balance in address_differences:
            difference = local_balance - api_balance
            print(
                "  {:<10} {:<20} {:<20} {:<20}".format(tick, f"{local_balance:.8f}", f"{api_balance:.8f}", f"{difference:.8f}")
            )


def find_first_mismatch(db):
    cursor = db.cursor()

    try:
        cursor.execute("SELECT MAX(block_index) as max_block FROM blocks")
        end_block = cursor.fetchone()["max_block"]

        if end_block is None:
            print("No blocks found in the database.")
            return None, None, None

        print(f"Checking blocks from {START_BLOCK} to {end_block}")

        local_hashes = get_all_local_ledger_hashes(cursor, START_BLOCK, end_block)

        pbar = tqdm(range(START_BLOCK, end_block + 1), desc="Checking blocks", unit="block")

        for block_index in pbar:
            pbar.set_description(f"Checking block {block_index}")

            local_hash = local_hashes.get(block_index)
            api_ledger_hash, api_ledger_validation = fetch_api_ledger_data(block_index)

            if local_hash != api_ledger_hash:
                print(f"\nMismatch found at block {block_index}")
                print(f"Local ledger hash: {local_hash}")
                print(f"API ledger hash: {api_ledger_hash}")

                # Calculate balances for the previous block
                previous_balances = calculate_balances(cursor, block_index - 1)

                # Get changes for the current block
                current_block_changes = get_block_changes(cursor, block_index)

                # Generate local valid_src20_str
                local_valid_src20_str = generate_valid_src20_str(previous_balances, current_block_changes)

                # Parse API balances
                api_balances = defaultdict(lambda: defaultdict(Decimal))
                if api_ledger_validation:
                    for entry in api_ledger_validation.split(";"):
                        tick, address, balance = entry.split(",")
                        api_balances[tick][address] = Decimal(balance)

                # Compare balances
                differences = compare_balances(previous_balances, api_balances)

                if differences:
                    print_balance_differences(differences)
                else:
                    print("\nNo differences in balances found, despite hash mismatch.")

                print(f"\nLocal valid_src20_str:\n{local_valid_src20_str}")
                print(f"\nAPI ledger validation:\n{api_ledger_validation}")

                return block_index, api_ledger_hash, api_ledger_validation

        print("\nNo mismatches found")
        return None, None, None

    finally:
        cursor.close()


def main():
    db = get_db_connection()
    try:
        print(f"Starting comparison from block {START_BLOCK}")
        mismatch_block, api_hash, api_validation = find_first_mismatch(db)
        if mismatch_block:
            print(f"\nFirst mismatch found at block: {mismatch_block}")
            print(f"API ledger hash: {api_hash}")
            print(f"API ledger validation: {api_validation}")

            # Get local hash for context
            cursor = db.cursor()
            cursor.execute("SELECT ledger_hash FROM blocks WHERE block_index = %s", (mismatch_block,))
            result = cursor.fetchone()
            local_hash = result["ledger_hash"] if result else None
            print(f"Local ledger hash: {local_hash}")
            cursor.close()
        else:
            print("\nNo mismatches found")
    finally:
        db.close()


if __name__ == "__main__":
    main()
