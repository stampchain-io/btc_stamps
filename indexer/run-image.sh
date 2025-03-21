#!/bin/bash

# Script to directly run a Docker image with proper environment
# Usage: ./run-image.sh DOCKER_IMAGE [OPTIONS]
# Example: ./run-image.sh btcstamps/indexer:latest
# Example with options: ./run-image.sh btcstamps/indexer:dev --with-db --detach

# Setup environment
cd "$(dirname "$0")"
SCRIPT_DIR=$(realpath "$(pwd)")
LOGS_DIR="${SCRIPT_DIR}/logs"
SUPERVISOR_LOGS_DIR="${LOGS_DIR}/supervisor"

# Create logs directories
mkdir -p "${LOGS_DIR}"
mkdir -p "${SUPERVISOR_LOGS_DIR}"
chmod -R 777 "${LOGS_DIR}"

# Check for image parameter
if [ -z "$1" ]; then
    echo "❌ Error: Docker image is required"
    echo "Usage: ./run-image.sh DOCKER_IMAGE [OPTIONS]"
    echo "Example: ./run-image.sh btcstamps/indexer:latest"
    echo "Options:"
    echo "  --with-db    Start with local MySQL container"
    echo "  --bridge     Use bridge networking instead of host"
    echo "  --detach     Run containers in the background"
    exit 1
fi

# Extract the image name
IMAGE_NAME="$1"
shift

# Default values
PROFILES=""
NETWORK_MODE="host"
COMPOSE_OPTS=""
ENV_FILE=".env.local"

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --with-db) PROFILES="--profile with-db"; shift ;;
        --bridge) NETWORK_MODE="bridge"; shift ;;
        --detach|-d) COMPOSE_OPTS="$COMPOSE_OPTS --detach"; shift ;;
        --env-file) ENV_FILE="$2"; shift 2 ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
done

# Ensure environment file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: Environment file $ENV_FILE does not exist"
    exit 1
fi

# Export variables for Docker Compose
export IMAGE_NAME
export NETWORK_MODE
# Don't mount code directory when using external image
export MOUNT_CODE_DIR=""
# Configure command and supervisord options
export SUPERVISORD_OPTIONS="-c /app/supervisord.conf"
export CONTAINER_COMMAND="sh -c 'mkdir -p /var/log/supervisor && chmod 777 /var/log/supervisor && mkdir -p /app/logs/supervisor && chmod 777 /app/logs/supervisor && supervisord \${SUPERVISORD_OPTIONS}'"

echo "🚀 Running container with image: $IMAGE_NAME"
echo "  • Network mode: $NETWORK_MODE"
echo "  • Environment file: $ENV_FILE"
echo "  • Additional options: $COMPOSE_OPTS $PROFILES"

# Run the container
set -e  # Exit on error
docker compose --env-file "$ENV_FILE" -f docker-compose.local.yml $PROFILES up $COMPOSE_OPTS

# If running in detached mode, show container status
if [[ $COMPOSE_OPTS =~ "--detach" ]]; then
    echo "✅ Container started in detached mode"
    echo "📋 To view logs: docker logs indexer-local-indexer-1 -f"
    echo "🛑 To stop: docker compose --env-file $ENV_FILE -f docker-compose.local.yml down"
fi 