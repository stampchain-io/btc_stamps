#!/bin/bash
# Script to flush Redis cache on ElastiCache

REDIS_HOST="stamps-app-cache.ycbgmb.0001.use1.cache.amazonaws.com"
REDIS_PORT="6379"

echo "==================================="
echo "Redis Cache Flush Script"
echo "==================================="
echo "Host: $REDIS_HOST"
echo "Port: $REDIS_PORT"
echo ""

# Install redis-cli if not present
if ! command -v redis-cli &> /dev/null; then
    echo "Installing redis-cli..."
    sudo apt-get update -qq
    sudo apt-get install -y redis-tools
fi

# Test connection
echo "Testing connection..."
redis-cli -h $REDIS_HOST -p $REDIS_PORT ping
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to connect to Redis"
    exit 1
fi

# Get info before flush
echo ""
echo "Current Redis status:"
KEYS_BEFORE=$(redis-cli -h $REDIS_HOST -p $REDIS_PORT dbsize | awk '{print $2}')
echo "Number of keys: $KEYS_BEFORE"

# Check for specific balance key
echo ""
echo "Checking for specific balance keys..."
redis-cli -h $REDIS_HOST -p $REDIS_PORT keys "*bc1qndwhntf80jv90kkkgvs67vp48hhpxeetrk9f5m*" | head -5

# Flush all databases
echo ""
echo "Flushing all Redis databases..."
redis-cli -h $REDIS_HOST -p $REDIS_PORT FLUSHALL

# Verify
echo ""
echo "Verifying flush..."
KEYS_AFTER=$(redis-cli -h $REDIS_HOST -p $REDIS_PORT dbsize | awk '{print $2}')
echo "Number of keys after flush: $KEYS_AFTER"

if [ "$KEYS_AFTER" == "0" ]; then
    echo ""
    echo "✓ SUCCESS: Redis cache has been flushed!"
else
    echo ""
    echo "⚠ WARNING: Redis still has $KEYS_AFTER keys"
fi

echo ""
echo "==================================="
echo "Flush complete!"
echo "===================================" 