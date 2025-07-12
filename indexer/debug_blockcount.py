#!/usr/bin/env python3
"""Debug script to check what getblockcount is returning"""

import os
import sys
import time

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import config
from index_core.backend import Backend


def main():
    backend = Backend()

    print("=== Bitcoin RPC Debug Info ===")
    print(f"RPC URL: {config.RPC_URL.replace(config.RPC_PASSWORD or '', '****')}")
    print(f"Using Quicknode: {bool(config.QUICKNODE_ENDPOINT)}")

    # Test getblockcount multiple times
    print("\n=== Testing getblockcount ===")

    # First call (might be cached)
    count1 = backend.getblockcount()
    print(f"First call: {count1}")

    # Invalidate cache and call again
    backend.invalidate_blockcount_cache()
    count2 = backend.getblockcount()
    print(f"After cache invalidation: {count2}")

    # Wait a bit and try again
    time.sleep(6)  # Wait longer than cache TTL
    count3 = backend.getblockcount()
    print(f"After 6 second wait: {count3}")

    # Try to get the latest block hash
    try:
        latest_hash = backend.getblockhash(count3)
        print(f"\nLatest block hash: {latest_hash}")

        # Get block details
        block_info = backend.getblock(latest_hash, True)
        print(f"Block height: {block_info.get('height')}")
        print(f"Block time: {block_info.get('time')}")
        print(f"Block mediantime: {block_info.get('mediantime')}")
    except Exception as e:
        print(f"Error getting block details: {e}")

    # Check if this is around the CP genesis block
    print(f"\nCP_STAMP_GENESIS_BLOCK: {config.CP_STAMP_GENESIS_BLOCK}")
    print(f"Difference from CP genesis: {count3 - config.CP_STAMP_GENESIS_BLOCK}")


if __name__ == "__main__":
    main()
