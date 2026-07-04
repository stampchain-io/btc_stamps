#!/usr/bin/env python3
"""
Fetch stamp transactions from the database for test fixtures.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from index_core.backend import Backend
from index_core.database_manager import DatabaseManager


def fetch_stamp_transactions_from_db(limit=10):
    """
    Fetch stamp transactions from the StampTableV4.

    Args:
        limit: Number of transactions to fetch

    Returns:
        List of transaction data dicts with txid, hex, and metadata
    """
    db_manager = DatabaseManager()
    backend = Backend()
    transactions = []

    try:
        with db_manager.get_cursor() as cursor:
            # Query for stamp transactions
            # Get a mix of different stamp types for testing
            query = """
                SELECT DISTINCT tx_hash, stamp, ident, cpid, block_index
                FROM StampTableV4
                WHERE tx_hash IS NOT NULL
                AND is_valid = 1
                ORDER BY block_index DESC
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            results = cursor.fetchall()

            print(f"Found {len(results)} stamp transactions in database")

            for row in results:
                tx_hash, stamp, ident, cpid, block_index = row

                try:
                    # Fetch the raw transaction hex from Bitcoin node
                    print(f"Fetching transaction {tx_hash} (stamp={stamp}, ident={ident})...")
                    raw_hex = backend.getrawtransaction(tx_hash)

                    transactions.append(
                        {
                            "txid": tx_hash,
                            "hex": raw_hex,
                            "description": f"Stamp {stamp} ({ident}) - CPID: {cpid}, Block: {block_index}",
                            "metadata": {"stamp": stamp, "ident": ident, "cpid": cpid, "block_index": block_index},
                        }
                    )
                    print(f"✓ Successfully fetched {tx_hash}")

                except Exception as e:
                    print(f"✗ Failed to fetch {tx_hash}: {e}")

    except Exception as e:
        print(f"Database error: {e}")

    return transactions


def save_fixtures(transactions, output_path):
    """Save transaction fixtures to JSON file."""
    fixtures_data = {
        "stamp_transactions": transactions,
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "generated_by": "fetch_stamp_transactions.py",
            "purpose": "Real stamp transactions from StampTableV4 for testing",
        },
    }

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save fixtures
    with open(output_path, "w") as f:
        json.dump(fixtures_data, f, indent=2)

    print(f"\nFixtures saved to: {output_path}")


def main():
    """Main function."""
    # Define output path
    output_path = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "stamp_transactions_fixtures.json"

    print("Fetching stamp transactions from database...")
    print("=" * 60)

    # Fetch transactions from database
    transactions = fetch_stamp_transactions_from_db(limit=5)

    if transactions:
        # Save fixtures
        save_fixtures(transactions, output_path)

        # Print summary
        print(f"\nSaved {len(transactions)} stamp transaction fixtures")
        print("\nTransaction types included:")
        for tx in transactions:
            print(f"  - {tx['metadata']['ident']}: {tx['txid'][:16]}...")
    else:
        print("\nNo transactions fetched. Check database connection.")


if __name__ == "__main__":
    main()
