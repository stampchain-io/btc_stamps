#!/bin/bash
set -e

# Debug output function
debug_info() {
    if [ "$DEBUG" = "1" ]; then
        echo "🔍 Container Environment:"
        echo "  • Python version: $(python --version)"
        echo "  • Working directory: $(pwd)"
        
        # Only show critical container-specific vars
        echo "  • Container Configuration:"
        env | grep -E 'DOCKER_|PYTHONPATH|DEBUG' | sed 's/=.*$/=****/'
        
        # Show Poetry environment
        if command -v poetry &> /dev/null; then
            echo "  • Poetry version: $(poetry --version)"
        fi
    fi
}

# Wait for MySQL
if [ "$DOCKER_CONTAINER" = "1" ]; then
    echo "🔄 Waiting for MySQL..."
    echo "  • Host: ${RDS_HOSTNAME:-localhost}"
    echo "  • Database: ${RDS_DATABASE:-btc_stamps}"
    echo "  • User: ${RDS_USER:-btc_stamps}"
    dockerize -wait "tcp://${RDS_HOSTNAME:-localhost}:3306" -timeout 60s
    echo "✅ MySQL is ready"
fi

# Create logs directory if not using Docker container logging
if [ "$DOCKER_CONTAINER" != "1" ]; then
    mkdir -p /app/logs
    chown indexer:indexer /app/logs
fi

# Show debug info if enabled
debug_info

echo "🚀 Starting application..."

# Execute the main command
exec "$@"
