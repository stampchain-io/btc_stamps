#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime

import requests

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from bitcoin.core import CBlock
from bitcoin.core.serialize import deserialize

from index_core.backend import Backend


def download_block(block_height, output_dir="data"):
    """Download a block and save it to a file."""
    print(f"Downloading block {block_height}...")

    # Initialize the backend
    backend = Backend()

    # Get the block hash
    block_hash = backend.getblockhash(block_height)
    print(f"Block hash: {block_hash}")

    # Get the block in raw format
    block_hex = backend.getblock(block_hash, 0)

    # Parse the block to get basic info
    block = deserialize(bytes.fromhex(block_hex), CBlock())
    tx_count = len(block.vtx)
    print(f"Block contains {tx_count} transactions")

    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Save the raw block data
    output_file = os.path.join(output_dir, f"block_{block_height}.dat")
    with open(output_file, "wb") as f:
        f.write(block.serialize())

    print(f"Block saved to {output_file}")

    # Save some metadata
    metadata = {
        "block_height": block_height,
        "block_hash": block_hash,
        "transaction_count": tx_count,
        "download_time": datetime.now().isoformat(),
    }

    metadata_file = os.path.join(output_dir, f"block_{block_height}_metadata.json")
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Metadata saved to {metadata_file}")

    return output_file


if __name__ == "__main__":
    # Default to block 784000 (a block after SRC-20 genesis)
    block_height = 784000

    # Allow specifying a different block height
    if len(sys.argv) > 1:
        try:
            block_height = int(sys.argv[1])
        except ValueError:
            print(f"Invalid block height: {sys.argv[1]}")
            sys.exit(1)

    output_dir = os.path.join(os.path.dirname(__file__), "data")
    download_block(block_height, output_dir)
