#!/usr/bin/env python3
import json
import os
import random
import sys
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from bitcoin.core import CBlock, CTransaction, CTxIn, CTxOut
from bitcoin.core.script import OP_RETURN, CScript


def create_test_block(tx_count=100, output_dir="data"):
    """Create a test block with a mix of regular and stamp transactions."""
    print(f"Creating test block with {tx_count} transactions...")

    # Create a block (we'll use CBlock since CMutableBlock is not available)
    block = CBlock()
    block.vtx = []

    # Create transactions
    for i in range(tx_count):
        # Create a transaction
        tx = CTransaction(vin=[CTxIn()], vout=[])

        # Add a regular output
        tx.vout.append(CTxOut(nValue=100000, scriptPubKey=CScript([OP_RETURN])))

        # For some transactions, add a stamp-like output
        if random.random() < 0.1:  # 10% of transactions will be stamp-like
            # Create a stamp-like output with the PREFIX at position 2
            script = CScript([OP_RETURN, b"", b"STAMP", b"", b""])
            tx.vout.append(CTxOut(nValue=0, scriptPubKey=script))
            print(f"Created stamp transaction {i}")

        # Add the transaction to the block
        block.vtx.append(tx)

    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Save the block data
    output_file = os.path.join(output_dir, "test_block.dat")
    with open(output_file, "wb") as f:
        f.write(block.serialize())

    print(f"Test block saved to {output_file}")

    # Save some metadata
    metadata = {
        "transaction_count": tx_count,
        "creation_time": datetime.now().isoformat(),
    }

    metadata_file = os.path.join(output_dir, "test_block_metadata.json")
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Metadata saved to {metadata_file}")

    return output_file


if __name__ == "__main__":
    # Default to 100 transactions
    tx_count = 100

    # Allow specifying a different transaction count
    if len(sys.argv) > 1:
        try:
            tx_count = int(sys.argv[1])
        except ValueError:
            print(f"Invalid transaction count: {sys.argv[1]}")
            sys.exit(1)

    output_dir = os.path.join(os.path.dirname(__file__), "data")
    create_test_block(tx_count, output_dir)
