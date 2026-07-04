#!/usr/bin/env python3
import json
import os
import random
import sys
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))


def create_stamp_transaction():
    """Create a transaction with a STAMP prefix at position 2."""
    # This is a simplified hex representation of a transaction with a STAMP prefix
    # The transaction has a P2WSH output (0x00 + 32 bytes) to match the valid pattern check
    tx_hex = (
        "0100000001000000000000000000000000000000000000000000000000000000000000000000000000"
        "00000000000200000000000000000a6a08005354414d50000000000000220020"
        "1111111111111111111111111111111111111111111111111111111111111111"
    )
    return tx_hex


def create_regular_transaction():
    """Create a regular transaction without a STAMP prefix."""
    # This is a simplified hex representation of a regular transaction
    tx_hex = (
        "0100000001000000000000000000000000000000000000000000000000000000000000000000000000"
        "00000000000100000000000000000a6a050000000000000000"
    )
    return tx_hex


def create_test_transactions(tx_count=100, stamp_ratio=0.1, output_dir="data"):
    """Create test transactions with a mix of regular and stamp transactions."""
    print(f"Creating {tx_count} test transactions with {stamp_ratio*100:.1f}% stamp transactions...")

    transactions = []
    stamp_count = 0

    for i in range(tx_count):
        if random.random() < stamp_ratio:
            tx_hex = create_stamp_transaction()
            transactions.append({"txid": f"stamp_tx_{i}", "hex": tx_hex})
            stamp_count += 1
        else:
            tx_hex = create_regular_transaction()
            transactions.append({"txid": f"regular_tx_{i}", "hex": tx_hex})

    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Save the transactions to a JSON file
    output_file = os.path.join(output_dir, "test_transactions.json")
    with open(output_file, "w") as f:
        json.dump(transactions, f, indent=2)

    print(f"Created {tx_count} transactions ({stamp_count} stamp transactions)")
    print(f"Transactions saved to {output_file}")

    # Save some metadata
    metadata = {
        "transaction_count": tx_count,
        "stamp_count": stamp_count,
        "stamp_ratio": stamp_ratio,
        "creation_time": datetime.now().isoformat(),
    }

    metadata_file = os.path.join(output_dir, "test_transactions_metadata.json")
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Metadata saved to {metadata_file}")

    return output_file


if __name__ == "__main__":
    # Default to 1000 transactions with 10% stamp transactions
    tx_count = 1000
    stamp_ratio = 0.1

    # Allow specifying a different transaction count
    if len(sys.argv) > 1:
        try:
            tx_count = int(sys.argv[1])
        except ValueError:
            print(f"Invalid transaction count: {sys.argv[1]}")
            sys.exit(1)

    # Allow specifying a different stamp ratio
    if len(sys.argv) > 2:
        try:
            stamp_ratio = float(sys.argv[2])
        except ValueError:
            print(f"Invalid stamp ratio: {sys.argv[2]}")
            sys.exit(1)

    output_dir = os.path.join(os.path.dirname(__file__), "data")
    create_test_transactions(tx_count, stamp_ratio, output_dir)
