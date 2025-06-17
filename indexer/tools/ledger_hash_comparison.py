import decimal
import os
import sys
import traceback
from collections import defaultdict
from decimal import Decimal

from dotenv import load_dotenv

# Add the parent directory to the Python path
if os.getcwd().endswith("/indexer"):
    sys.path.append(os.getcwd())
    dotenv_path = os.path.join(os.getcwd(), ".env")
else:
    sys.path.append(os.path.join(os.getcwd(), "indexer"))
    dotenv_path = os.path.join(os.getcwd(), "indexer/.env")

import pymysql as mysql

# Load the environment variables
load_dotenv(dotenv_path=dotenv_path, override=True)

# Constants
SRC20_VALID_TABLE = "SRC20Valid"
START_BLOCK = 794352  # Focus on our problematic block
END_BLOCK = 794352  # Only check this specific block

# Try to import the fetch_api_ledger_data function from the codebase
try:
    from index_core.src20 import fetch_api_ledger_data, parse_balances
except ImportError:
    # If we can't import it, define a simple version
    def fetch_api_ledger_data(block_index):
        print(f"Warning: Using stub fetch_api_ledger_data function. No API data will be available.")
        return None, None

    def parse_balances(balance_str):
        balances = defaultdict(lambda: defaultdict(Decimal))
        if not balance_str:
            return balances

        for entry in balance_str.split(";"):
            if entry:  # Skip empty entries
                parts = entry.split(",")
                if len(parts) == 3:  # Ensure we have all three parts
                    tick, address, balance = parts
                    try:
                        balances[tick][address] = Decimal(balance)
                    except (decimal.InvalidOperation, ValueError) as e:
                        print(f"Error parsing balance '{balance}' for {tick}/{address}: {e}")
        return balances


def get_prod_db_connection():
    """Connect to the production database using environment variables"""
    try:
        print("Connecting to production database...")
        print(f"Host: {os.environ.get('ST3_HOSTNAME')}")
        print(f"Database: {os.environ.get('PROD_DATABASE', 'btc_stamps')}")

        return mysql.connect(
            host=os.environ.get("ST3_HOSTNAME"),
            user=os.environ.get("ST3_USER"),
            password=os.environ.get("ST3_PASSWORD"),
            database=os.environ.get("PROD_DATABASE", "btc_stamps"),
            charset="utf8mb4",
            cursorclass=mysql.cursors.DictCursor,
        )
    except Exception as e:
        print(f"Error connecting to production database: {e}")
        raise


def get_db_connection():
    """Connect to the local development database"""
    try:
        print("Connecting to local database...")
        print(f"Host: {os.environ.get('RDS_HOSTNAME')}")
        print(f"Database: {os.environ.get('RDS_DATABASE', 'btc_stamps')}")

        return mysql.connect(
            host=os.environ.get("RDS_HOSTNAME"),
            user=os.environ.get("RDS_USER"),
            password=os.environ.get("RDS_PASSWORD"),
            database=os.environ.get("RDS_DATABASE", "btc_stamps"),
            charset="utf8mb4",
            cursorclass=mysql.cursors.DictCursor,
        )
    except Exception as e:
        print(f"Error connecting to local database: {e}")
        raise


def get_all_local_ledger_hashes(cursor, start_block, end_block):
    """Get all ledger hashes from the local database for the specified block range"""
    cursor.execute("SELECT block_index, ledger_hash FROM blocks WHERE block_index BETWEEN %s AND %s", (start_block, end_block))
    return {row["block_index"]: row["ledger_hash"] for row in cursor.fetchall()}


def calculate_balances(cursor, block_index):
    """Calculate SRC20 balances up to the specified block"""
    print(f"Calculating balances up to block {block_index}...")

    query = f"""
    SELECT op, creator, destination, tick, tick_hash, amt
    FROM {SRC20_VALID_TABLE}
    WHERE block_index <= %s AND (op = 'TRANSFER' OR op = 'MINT') AND amt > 0
    ORDER BY block_index, tx_index
    """  # nosec B608 - SRC20_VALID_TABLE is a static constant from config.py
    cursor.execute(query, (block_index,))
    src20_valid_list = cursor.fetchall()
    print(f"Found {len(src20_valid_list)} valid SRC20 transactions up to block {block_index}")

    balances = defaultdict(lambda: defaultdict(Decimal))
    error_count = 0

    for row in src20_valid_list:
        try:
            op = row["op"]
            creator = row["creator"]
            destination = row["destination"]
            tick = row["tick"]
            tick_hash = row["tick_hash"]

            # Handle potential string or None values for amt
            amt_str = row["amt"]
            if amt_str is None:
                print(f"Warning: None value for amt in {op} operation for {tick}")
                continue

            try:
                amt = Decimal(str(amt_str))
            except (decimal.InvalidOperation, ValueError) as e:
                print(f"Error converting amt '{amt_str}' to Decimal: {e}")
                error_count += 1
                continue

            if op == "MINT":
                balances[tick][destination] += amt
            elif op == "TRANSFER":
                balances[tick][creator] -= amt
                balances[tick][destination] += amt
        except Exception as e:
            print(f"Error processing row: {row} - {e}")
            error_count += 1
            continue

    if error_count > 0:
        print(f"Warning: Encountered {error_count} errors while calculating balances")

    # Print summary of balances
    total_balances = sum(len(addresses) for addresses in balances.values())
    print(f"Calculated {total_balances} balances across {len(balances)} ticks")

    return balances


def get_block_changes(cursor, block_index):
    """Get SRC20 changes for the specified block"""
    print(f"Getting SRC20 changes for block {block_index}...")

    query = f"""
    SELECT op, creator, destination, tick, tick_hash, amt
    FROM {SRC20_VALID_TABLE}
    WHERE block_index = %s AND (op = 'TRANSFER' OR op = 'MINT') AND amt > 0
    ORDER BY tx_index
    """  # nosec B608 - SRC20_VALID_TABLE is a static constant from config.py
    cursor.execute(query, (block_index,))
    changes = cursor.fetchall()
    print(f"Found {len(changes)} SRC20 changes in block {block_index}")

    return changes


def generate_valid_src20_str(balances, changes):
    """Generate the valid_src20_str used for ledger hash calculation"""
    print("Generating valid_src20_str from balances and changes...")

    # Create a deep copy of balances to avoid modifying the original
    updated_balances = defaultdict(lambda: defaultdict(Decimal))
    for tick, addresses in balances.items():
        for address, balance in addresses.items():
            updated_balances[tick][address] = balance

    # Apply changes
    for row in changes:
        try:
            op = row["op"]
            creator = row["creator"]
            destination = row["destination"]
            tick = row["tick"]

            # Handle potential string or None values for amt
            amt_str = row["amt"]
            if amt_str is None:
                print(f"Warning: None value for amt in {op} operation for {tick}")
                continue

            try:
                amt = Decimal(str(amt_str))
                print(f"Converted amt '{amt_str}' to Decimal: {amt}")
            except (decimal.InvalidOperation, ValueError) as e:
                print(f"Error converting amt '{amt_str}' to Decimal: {e}")
                continue

            if op == "MINT":
                print(f"MINT: {tick} to {destination}, amount: {amt}")
                old_balance = updated_balances[tick][destination]
                updated_balances[tick][destination] = updated_balances[tick][destination] + amt
                print(f"  Balance update: {old_balance} -> {updated_balances[tick][destination]}")
            elif op == "TRANSFER":
                print(f"TRANSFER: {tick} from {creator} to {destination}, amount: {amt}")
                old_src_balance = updated_balances[tick][creator]
                old_dst_balance = updated_balances[tick][destination]
                updated_balances[tick][creator] = updated_balances[tick][creator] - amt
                updated_balances[tick][destination] = updated_balances[tick][destination] + amt
                print(f"  Source balance update: {old_src_balance} -> {updated_balances[tick][creator]}")
                print(f"  Destination balance update: {old_dst_balance} -> {updated_balances[tick][destination]}")
        except Exception as e:
            print(f"Error processing row: {row} - {e}")
            continue

    # Generate the valid_src20_str
    valid_src20_list = []
    for tick in sorted(updated_balances.keys()):
        for address in sorted(updated_balances[tick].keys()):
            balance = updated_balances[tick][address]
            if balance > 0:
                # Format the balance to match the production format
                # This is critical for hash calculation
                balance_str = str(balance)
                print(f"Original balance string for {tick}/{address}: '{balance_str}'")
                if "." in balance_str:
                    # Remove trailing zeros
                    balance_str = balance_str.rstrip("0").rstrip(".")
                print(f"Formatted balance string for {tick}/{address}: '{balance_str}'")
                valid_src20_list.append(f"{tick},{address},{balance_str}")

    valid_src20_str = ";".join(valid_src20_list)
    print(f"Generated valid_src20_str with {len(valid_src20_list)} entries")

    return valid_src20_str


def compare_balances(local_balances, api_balances):
    """Compare local and API balances to find differences"""
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

            # Add detailed logging for balance comparison
            if local_balance != api_balance:
                print(f"Balance mismatch for {tick}/{address}:")
                print(f"  Local: {local_balance} (type: {type(local_balance)}, repr: {repr(local_balance)})")
                print(f"  API:   {api_balance} (type: {type(api_balance)}, repr: {repr(api_balance)})")

                # Check if the difference is due to precision/rounding
                if abs(local_balance - api_balance) < Decimal("0.000000001"):
                    print(f"  NOTE: Difference is very small, likely due to precision/rounding")

                address_differences.append((tick, local_balance, api_balance))

        if address_differences:
            differences.append((address, address_differences))

    return differences


def print_balance_differences(differences):
    """Print the differences between local and API balances"""
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


def find_first_mismatch(local_db, prod_db=None):
    """Find the first ledger hash mismatch between local and production databases"""
    cursor = local_db.cursor()
    prod_cursor = prod_db.cursor() if prod_db else None

    try:
        print(f"Checking blocks from {START_BLOCK} to {END_BLOCK}")

        local_hashes = get_all_local_ledger_hashes(cursor, START_BLOCK, END_BLOCK)
        print(f"Retrieved {len(local_hashes)} local ledger hashes")

        for block_index in range(START_BLOCK, END_BLOCK + 1):
            print(f"\n{'='*80}")
            print(f"Checking block {block_index}")
            print(f"{'='*80}")

            local_hash = local_hashes.get(block_index)
            print(f"Local ledger hash: {local_hash}")

            # If we have a production database connection, get the hash directly
            if prod_cursor:
                print("Getting production ledger hash...")
                prod_cursor.execute("SELECT ledger_hash FROM blocks WHERE block_index = %s", (block_index,))
                prod_result = prod_cursor.fetchone()
                api_ledger_hash = prod_result["ledger_hash"] if prod_result else None
                print(f"Production ledger hash: {api_ledger_hash}")

                # Get validation data from production
                if api_ledger_hash:
                    print("Getting production ledger validation data...")
                    try:
                        prod_cursor.execute(
                            f"""
                            SELECT GROUP_CONCAT(CONCAT(tick, ',', address, ',', balance) SEPARATOR ';') as validation_data
                            FROM (
                                SELECT tick, address, SUM(balance) as balance
                                FROM src20_balances
                                WHERE block_index = %s AND balance > 0
                                GROUP BY tick, address
                                ORDER BY tick, address
                            ) as balances
                            """,  # nosec B608 - This is a static SQL query with no dynamic table names
                            (block_index,),
                        )
                        validation_result = prod_cursor.fetchone()
                        api_ledger_validation = validation_result["validation_data"] if validation_result else None
                        print(
                            f"Retrieved production ledger validation data: {len(api_ledger_validation) if api_ledger_validation else 0} characters"
                        )
                    except Exception as e:
                        print(f"Error getting production ledger validation data: {e}")
                        print("Falling back to API for ledger validation data...")
                        _, api_ledger_validation = fetch_api_ledger_data(block_index)
                        print(
                            f"API ledger validation data: {len(api_ledger_validation) if api_ledger_validation else 0} characters"
                        )
            else:
                # Fall back to API if no direct production connection
                print("No production database connection, fetching from API...")
                api_ledger_hash, api_ledger_validation = fetch_api_ledger_data(block_index)
                print(f"API ledger hash: {api_ledger_hash}")
                print(f"API ledger validation data: {len(api_ledger_validation) if api_ledger_validation else 0} characters")

            if local_hash != api_ledger_hash:
                print(f"\nMismatch found at block {block_index}")
                print(f"Local ledger hash: {local_hash}")
                print(f"API/Production ledger hash: {api_ledger_hash}")

                # Calculate balances for the previous block
                previous_balances = calculate_balances(cursor, block_index - 1)

                # Get changes for the current block
                current_block_changes = get_block_changes(cursor, block_index)

                # Generate local valid_src20_str
                local_valid_src20_str = generate_valid_src20_str(previous_balances, current_block_changes)

                # Parse API balances
                api_balances = defaultdict(lambda: defaultdict(Decimal))
                if api_ledger_validation:
                    print("Parsing API/Production ledger validation data...")
                    for entry in api_ledger_validation.split(";"):
                        if entry:  # Skip empty entries
                            parts = entry.split(",")
                            if len(parts) == 3:  # Ensure we have all three parts
                                tick, address, balance = parts
                                try:
                                    api_balances[tick][address] = Decimal(balance)
                                except (decimal.InvalidOperation, ValueError) as e:
                                    print(f"Error parsing balance '{balance}' for {tick}/{address}: {e}")

                # Compare balances
                differences = compare_balances(previous_balances, api_balances)

                if differences:
                    print_balance_differences(differences)
                else:
                    print("\nNo differences in balances found, despite hash mismatch.")

                    # Check for string format differences
                    if api_ledger_validation:
                        local_entries = set(local_valid_src20_str.split(";"))
                        api_entries = set(api_ledger_validation.split(";"))

                        print(f"\nString format comparison:")
                        print(f"  Local entries count: {len(local_entries)}")
                        print(f"  API entries count: {len(api_entries)}")

                        # Check for differences in the sets
                        differences = local_entries.symmetric_difference(api_entries)
                        if differences:
                            print(f"\nFound {len(differences)} differences in string format:")
                            for i, diff in enumerate(sorted(differences)):
                                print(f"  {i+1}. {diff}")
                                if i >= 9:  # Show only first 10 differences
                                    print(f"  ... and {len(differences) - 10} more")
                                    break

                print(f"\nLocal valid_src20_str:\n{local_valid_src20_str}")
                print(f"\nAPI ledger validation:\n{api_ledger_validation}")

                return block_index, api_ledger_hash, api_ledger_validation

        print("\nNo mismatches found")
        return None, None, None

    except Exception as e:
        print(f"Error in find_first_mismatch: {e}")
        traceback.print_exc()
        return None, None, None
    finally:
        cursor.close()
        if prod_cursor:
            prod_cursor.close()


# Add a function to get detailed SRC20 transactions for a block
def get_detailed_src20_transactions(cursor, block_index):
    """Get detailed SRC20 transactions for a specific block"""
    print(f"\n{'='*80}")
    print(f"DETAILED SRC20 TRANSACTIONS FOR BLOCK {block_index}")
    print(f"{'='*80}")

    query = f"""
    SELECT * FROM {SRC20_VALID_TABLE}
    WHERE block_index = %s
    ORDER BY tx_index
    """  # nosec B608 - SRC20_VALID_TABLE is a static constant from config.py

    try:
        cursor.execute(query, (block_index,))
        transactions = cursor.fetchall()

        if not transactions:
            print(f"No SRC20 transactions found for block {block_index}")
            return []

        print(f"Found {len(transactions)} SRC20 transactions in block {block_index}")

        for i, tx in enumerate(transactions):
            print(f"\nTransaction #{i+1}:")
            for key, value in tx.items():
                print(f"  {key}: {value}")

        return transactions
    except Exception as e:
        print(f"Error fetching SRC20 transactions: {e}")
        return []


def main():
    """Main function to run the ledger hash comparison"""
    print("Starting ledger hash comparison...")

    try:
        # Connect to local database
        local_db = get_db_connection()
        local_cursor = local_db.cursor()

        # Try to connect to production database
        try:
            prod_db = get_prod_db_connection()
            prod_cursor = prod_db.cursor()
            print("Successfully connected to production database")

            # Get detailed SRC20 transactions from production
            print("\nFetching SRC20 transactions from production database...")
            prod_transactions = get_detailed_src20_transactions(prod_cursor, START_BLOCK)

            # Get detailed SRC20 transactions from local
            print("\nFetching SRC20 transactions from local database...")
            local_transactions = get_detailed_src20_transactions(local_cursor, START_BLOCK)

            # Compare transaction counts
            print(f"\nSRC20 Transaction comparison for block {START_BLOCK}:")
            print(f"Production: {len(prod_transactions)} transactions")
            print(f"Local: {len(local_transactions)} transactions")

            # Check if the block exists in both databases
            local_cursor.execute("SELECT * FROM blocks WHERE block_index = %s", (START_BLOCK,))
            local_block = local_cursor.fetchone()

            prod_cursor.execute("SELECT * FROM blocks WHERE block_index = %s", (START_BLOCK,))
            prod_block = prod_cursor.fetchone()

            print(f"\nBlock {START_BLOCK} existence:")
            print(f"Production: {'Exists' if prod_block else 'Does not exist'}")
            print(f"Local: {'Exists' if local_block else 'Does not exist'}")

            if prod_block and local_block:
                print(f"\nBlock {START_BLOCK} details:")
                print(f"Production ledger_hash: {prod_block.get('ledger_hash', 'None')}")
                print(f"Local ledger_hash: {local_block.get('ledger_hash', 'None')}")

        except Exception as e:
            print(f"Could not connect to production database: {e}")
            print("Falling back to API for ledger hash comparison")
            prod_db = None
            prod_cursor = None

        print(f"\nStarting comparison from block {START_BLOCK}")
        mismatch_block, api_hash, api_validation = find_first_mismatch(local_db, prod_db)

        if mismatch_block:
            print(f"\nFirst mismatch found at block: {mismatch_block}")
            print(f"API/Production ledger hash: {api_hash}")

            # Get local hash for context
            cursor = local_db.cursor()
            cursor.execute("SELECT ledger_hash FROM blocks WHERE block_index = %s", (mismatch_block,))
            result = cursor.fetchone()
            local_hash = result["ledger_hash"] if result else None
            print(f"Local ledger hash: {local_hash}")
            cursor.close()
        else:
            print("\nNo mismatches found")

    except Exception as e:
        print(f"Error in main: {e}")
        traceback.print_exc()
    finally:
        if "local_cursor" in locals():
            local_cursor.close()
        if "prod_cursor" in locals() and prod_cursor:
            prod_cursor.close()
        if "local_db" in locals():
            local_db.close()
        if "prod_db" in locals() and prod_db:
            prod_db.close()


if __name__ == "__main__":
    main()
