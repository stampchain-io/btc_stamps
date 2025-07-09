#!/usr/bin/env python3
"""
Script to flush Redis cache on ElastiCache.
Must be run from an EC2 instance within the same VPC as the ElastiCache cluster.
"""

import os
import sys

import redis

# ElastiCache endpoint
REDIS_HOST = "stamps-app-cache.ycbgmb.0001.use1.cache.amazonaws.com"
REDIS_PORT = 6379  # Default Redis port


def flush_redis_cache():
    """Connect to Redis and flush all data."""
    try:
        # Connect to Redis
        # Note: If your Redis requires a password, add password='your-password'
        print(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)

        # Test connection
        r.ping()
        print("✓ Connected successfully")

        # Get some stats before flushing
        info = r.info()
        print(f"\nCurrent Redis stats:")
        print(f"  Used memory: {info.get('used_memory_human', 'N/A')}")
        print(f"  Number of keys: {r.dbsize()}")

        # Ask for confirmation
        response = input("\n⚠️  Are you sure you want to flush ALL Redis cache? (yes/no): ")
        if response.lower() != "yes":
            print("Flush cancelled.")
            return

        # Flush all databases
        print("\nFlushing all Redis databases...")
        r.flushall()

        # Verify
        new_size = r.dbsize()
        print(f"✓ Flush complete. Current number of keys: {new_size}")

        # Check specific keys related to SRC20 balances if needed
        # Example: Check if any balance keys exist
        balance_keys = r.keys("*balance*")
        print(f"  Balance-related keys remaining: {len(balance_keys)}")

    except redis.ConnectionError as e:
        print(f"❌ Failed to connect to Redis: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure this script is run from an EC2 instance in the same VPC")
        print("2. Check that security groups allow connection on port 6379")
        print("3. Verify the ElastiCache endpoint is correct")
        print("4. Check if Redis requires authentication")
        sys.exit(1)
    except redis.ResponseError as e:
        print(f"❌ Redis command failed: {e}")
        print("\nThis might mean Redis requires authentication.")
        print("Add password parameter to the Redis connection.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


def check_specific_keys():
    """Check for specific cached keys related to our address."""
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

        # Look for keys related to our problematic address
        address = "bc1qndwhntf80jv90kkkgvs67vp48hhpxeetrk9f5m"

        print(f"\nChecking for cached keys related to {address}...")

        # Common key patterns to check
        patterns = [
            f"*{address}*",
            "*balance*stamp*",
            "*src20*stamp*",
            f"*904239*",  # The block where API is stuck
        ]

        for pattern in patterns:
            keys = r.keys(pattern)
            if keys:
                print(f"\nFound {len(keys)} keys matching pattern '{pattern}':")
                for key in keys[:5]:  # Show first 5
                    try:
                        ttl = r.ttl(key)
                        key_type = r.type(key)
                        print(f"  {key} (type: {key_type}, TTL: {ttl}s)")
                    except:
                        print(f"  {key}")

    except Exception as e:
        print(f"Error checking keys: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        check_specific_keys()
    else:
        flush_redis_cache()
