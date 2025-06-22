#!/usr/bin/env python3
"""
Tool to fetch raw block hex data from Bitcoin node for testing purposes.

This tool fetches raw block data (verbosity=0) which is needed for testing
the Rust parser's block parsing functionality.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from index_core.backend import Backend

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def fetch_block_hex(block_height: int, output_dir: Path) -> Path:
    """
    Fetch raw block hex data from Bitcoin node.

    Args:
        block_height: Block height to fetch
        output_dir: Directory to save the output

    Returns:
        Path to the saved file
    """
    logger.info(f"Fetching raw block hex for height {block_height}...")

    # Initialize the backend
    backend = Backend()

    # Get the block hash
    block_hash = backend.getblockhash(block_height)
    logger.info(f"Block hash: {block_hash}")

    # Get the block in raw hex format (verbosity=0)
    block_hex = backend.getblock(block_hash, 0)

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Prepare the data structure
    block_data = {
        "height": block_height,
        "hash": block_hash,
        "hex": block_hex,
        "hex_size": len(block_hex) // 2,  # Size in bytes
        "description": f"Raw block hex data for block {block_height}",
    }

    # Save to JSON file
    output_file = output_dir / f"block_{block_height}_hex.json"
    with open(output_file, "w") as f:
        json.dump(block_data, f, indent=2)

    logger.info(f"Saved block hex data to {output_file}")
    logger.info(f"Block hex size: {len(block_hex)} characters ({len(block_hex) // 2} bytes)")

    return output_file


def main():
    parser = argparse.ArgumentParser(description="Fetch raw block hex data from Bitcoin node for testing")
    parser.add_argument("height", type=int, help="Block height to fetch")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/fixtures/block_hex"),
        help="Output directory (default: tests/fixtures/block_hex)",
    )
    parser.add_argument("--multiple", type=str, help="Fetch multiple blocks, e.g., '779652,780000' or '779652-779655'")

    args = parser.parse_args()

    # Determine which blocks to fetch
    blocks_to_fetch = []

    if args.multiple:
        # Parse multiple block specification
        for part in args.multiple.split(","):
            part = part.strip()
            if "-" in part:
                start, end = map(int, part.split("-", 1))
                blocks_to_fetch.extend(range(start, end + 1))
            else:
                blocks_to_fetch.append(int(part))
    else:
        blocks_to_fetch.append(args.height)

    # Remove duplicates and sort
    blocks_to_fetch = sorted(set(blocks_to_fetch))

    logger.info(f"Will fetch {len(blocks_to_fetch)} block(s): {blocks_to_fetch}")

    # Fetch each block
    for block_height in blocks_to_fetch:
        try:
            fetch_block_hex(block_height, args.output_dir)
        except Exception as e:
            logger.error(f"Failed to fetch block {block_height}: {e}")
            if len(blocks_to_fetch) == 1:
                sys.exit(1)

    logger.info("Done!")


if __name__ == "__main__":
    main()
