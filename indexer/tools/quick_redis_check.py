#!/usr/bin/env python3
"""
Quick Redis check without scanning all keys.
"""

import sys

import redis

REDIS_HOST = "stamps-app-cache.ycbgmb.0001.use1.cache.amazonaws.com"
REDIS_PORT = 6379

try:
    # Connect to Redis
    print(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)

    # Test connection
    r.ping()
    print("✓ Connected successfully")

    # Get basic info
    info = r.info()
    print(f"\nRedis Info:")
    print(f"  Used memory: {info.get('used_memory_human', 'N/A')}")
    print(f"  Total keys: {r.dbsize()}")

    # Try to get specific keys without scanning
    test_address = "bc1qndwhntf80jv90kkkgvs67vp48hhpxeetrk9f5m"

    # Common cache key patterns that APIs might use
    possible_keys = [
        f"balance:{test_address}:stamp",
        f"src20:balance:{test_address}:stamp",
        f"api:balance:{test_address}:stamp",
        f"{test_address}:stamp",
        f"stamp:{test_address}",
        f"balance:stamp:{test_address}",
    ]

    print(f"\nChecking specific keys for {test_address}:")
    found_keys = []
    for key in possible_keys:
        if r.exists(key):
            value = r.get(key)
            ttl = r.ttl(key)
            found_keys.append(key)
            print(f"  ✓ Found: {key}")
            print(f"    Value: {value}")
            print(f"    TTL: {ttl} seconds")

    if not found_keys:
        print("  No keys found with common patterns")

    # Sample a few random keys to understand the key structure
    print("\nSampling 5 random keys to understand structure:")
    sample_keys = r.randomkey()
    if sample_keys:
        for i in range(min(5, r.dbsize())):
            key = r.randomkey()
            if key:
                key_type = r.type(key)
                print(f"  {key} (type: {key_type})")

except redis.ConnectionError as e:
    print(f"❌ Failed to connect to Redis: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
