#!/bin/bash
set -e

# Configuration
host="${1:-${RDS_HOSTNAME:-localhost}}"
port="${2:-3306}"
timeout="${3:-60}"
wait_interval=1

# Print startup message
echo "🔄 Waiting for MySQL..."
echo "  • Host: $host"
echo "  • Port: $port"
echo "  • Timeout: ${timeout}s"

# Calculate end time
end_time=$(($(date +%s) + timeout))

# Try to connect until timeout
while [ $(date +%s) -lt $end_time ]; do
    if nc -z "$host" "$port" > /dev/null 2>&1; then
        echo "✅ MySQL is ready"
        exit 0
    fi
    echo "⏳ MySQL not available yet, waiting ${wait_interval}s..."
    sleep $wait_interval
done

echo "❌ Timed out waiting for MySQL at $host:$port after ${timeout}s"
exit 1 