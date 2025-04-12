#!/bin/bash
set -e

# Debug output function
debug_info() {
    if [ "$DEBUG" = "1" ]; then
        echo "🔍 Container Environment:"
        echo "  • Python version: $(python --version)"
        echo "  • Working directory: $(pwd)"

        echo "  • Container Configuration:"
        env | grep -E 'DOCKER_|PYTHONPATH|DEBUG|LD_LIBRARY_PATH' | sed 's/=.*$/=****/'

        if command -v poetry &> /dev/null; then
            echo "  • Poetry version: $(poetry --version)"
        fi
    fi
}

# Only for Alpine-based containers (if using apk)
install_openssl_libs() {
    if [ -f /etc/alpine-release ]; then
        echo "Installing additional OpenSSL libraries..."
        apk add --no-cache libssl3 libcrypto3 || true
    fi
}

# Wait for MySQL (only in Dockerized mode)
wait_for_mysql_if_needed() {
    if [ "$DOCKER_CONTAINER" = "1" ] && [ -x /app/wait-for-mysql.sh ]; then
        /app/wait-for-mysql.sh "${RDS_HOSTNAME:-localhost}" "3306" "60"
    fi
}

# Prepare logs directory (non-Docker logging)
prepare_logs() {
    if [ "$DOCKER_CONTAINER" != "1" ]; then
        mkdir -p /app/logs
        chown indexer:indexer /app/logs
    fi
}

# Main setup
install_openssl_libs
wait_for_mysql_if_needed
prepare_logs
debug_info

echo "🚀 Starting application..."

# ⚠️ DO NOT run poetry install here!
# All dependencies and the project itself must be installed at build time.

# Execute the main command passed to the container (e.g., poetry run indexer)
exec "$@"

