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
        env | grep -E 'DOCKER_|PYTHONPATH|DEBUG|LD_LIBRARY_PATH' | sed 's/=.*$/=****/'
        
        # Show Poetry environment
        if command -v poetry &> /dev/null; then
            echo "  • Poetry version: $(poetry --version)"
        fi
    fi
}

# Install additional OpenSSL libraries if needed
if [ "$DOCKER_CONTAINER" = "1" ]; then
    # Run as root if we have permissions, otherwise skip
    if [ "$(id -u)" = "0" ]; then
        echo "Installing additional OpenSSL libraries..."
        apk add --no-cache libssl3 libcrypto3 2>/dev/null || true
    fi
fi

# Wait for MySQL
if [ "$DOCKER_CONTAINER" = "1" ]; then
    # Using our custom wait-for-mysql script instead of dockerize
    /app/wait-for-mysql.sh "${RDS_HOSTNAME:-localhost}" "3306" "60"
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
