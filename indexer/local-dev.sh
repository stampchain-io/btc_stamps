#!/bin/bash

# Set up environment early
cd "$(dirname "$0")"
SCRIPT_DIR=$(realpath "$(pwd)")
LOGS_DIR="${SCRIPT_DIR}/logs"

# Create Docker environment file if it doesn't exist
if [ ! -f .env.local ]; then
    echo "📝 Creating .env.local file..."
    cat > .env.local << EOL
PWD=${SCRIPT_DIR}
COMPOSE_PROJECT_DIR=${SCRIPT_DIR}
COMPOSE_PROJECT_NAME=indexer-local
DOCKER_BUILDKIT=1
COMPOSE_DOCKER_CLI_BUILD=1
COMPOSE_IGNORE_ORPHANS=true
DOCKER_CONTAINER=1
PYTHONUNBUFFERED=1
DEBUG=1
RDS_DATABASE=btc_stamps
RDS_USER=btc_stamps
RDS_PASSWORD=password
RDS_HOSTNAME=localhost
CP_RPC_URL=http://localhost:4000/api/
CP_RPC_USER=rpc
CP_RPC_PASSWORD=rpc
RPC_IP=localhost
RPC_USER=rpc
RPC_PASSWORD=rpc
RPC_PORT=8332
QUI
EOL
else
    echo "📄 Using existing .env.local file"
fi

# Function to check RPC configuration
check_rpc_config() {
    local file=$1
    # Check if QUICKNODE_URL exists and has a value
    if grep -q "^QUICKNODE_URL=" "$file" && [ -n "$(grep '^QUICKNODE_URL=' "$file" | cut -d'=' -f2)" ]; then
        # If using QUICKNODE_URL, add RPC_TOKEN if missing
        if ! grep -q "^RPC_TOKEN=" "$file"; then
            echo "  ➕ Adding RPC_TOKEN for Quicknode configuration"
            echo "RPC_TOKEN=${required_vars[RPC_TOKEN]}" >> "$file"
        fi
    else
        # If not using QUICKNODE_URL, ensure standard RPC variables are present
        for var in "RPC_IP" "RPC_USER" "RPC_PASSWORD" "RPC_PORT"; do
            if ! grep -q "^${var}=" "$file"; then
                echo "  ➕ Adding missing variable: ${var}"
                echo "${var}=${required_vars[$var]}" >> "$file"
            fi
        done
    fi
}

# Check for required variables in existing .env.local
if [ -f .env.local ]; then
    echo "🔍 Checking environment variables..."
    declare -A required_vars=(
        ["PWD"]="${SCRIPT_DIR}"
        ["COMPOSE_PROJECT_DIR"]="${SCRIPT_DIR}"
        ["COMPOSE_PROJECT_NAME"]="indexer-local"
        ["DOCKER_BUILDKIT"]="1"
        ["COMPOSE_DOCKER_CLI_BUILD"]="1"
        ["COMPOSE_IGNORE_ORPHANS"]="true"
        ["DOCKER_CONTAINER"]="1"
        ["PYTHONUNBUFFERED"]="1"
        ["DEBUG"]="1"
        ["RDS_DATABASE"]="btc_stamps"
        ["RDS_USER"]="btc_stamps"
        ["RDS_PASSWORD"]="Prun3d"
        ["RDS_HOSTNAME"]="localhost"
        ["CP_RPC_URL"]="http://localhost:4000/api/"
        ["CP_RPC_USER"]="rpc"
        ["CP_RPC_PASSWORD"]="rpc"
        # RPC configuration options
        ["QUICKNODE_URL"]=""  # Empty default
        ["RPC_TOKEN"]=""      # Empty default
        ["RPC_IP"]="localhost"
        ["RPC_USER"]="rpc"
        ["RPC_PASSWORD"]="rpc"
        ["RPC_PORT"]="8332"
    )

    for var in "${!required_vars[@]}"; do
        # Skip RPC variables as they're handled separately
        if [[ "$var" =~ ^(QUICKNODE_URL|RPC_TOKEN|RPC_IP|RPC_USER|RPC_PASSWORD|RPC_PORT)$ ]]; then
            continue
        fi
        if ! grep -q "^${var}=" .env.local; then
            echo "  ➕ Adding missing variable: ${var}"
            echo "${var}=${required_vars[$var]}" >> .env.local
        fi
    done

    # Handle RPC configuration
    check_rpc_config ".env.local"
fi

# Ensure environment variables are set in .env.local
if [ -f .env.local ]; then
    if ! grep -q "^PWD=" .env.local; then
        echo "PWD=${SCRIPT_DIR}" >> .env.local
    fi
    if ! grep -q "^COMPOSE_PROJECT_DIR=" .env.local; then
        echo "COMPOSE_PROJECT_DIR=${SCRIPT_DIR}" >> .env.local
    fi
fi

# Default values
PROFILES=""
NETWORK_MODE="host"
COMPOSE_OPTS=""
RUN_TESTS=false
CLEANUP=false
IMAGE_NAME="btc_stamps/indexer:local-dev"  # Default image name
INSTALL_DEV="true"  # Default to dev mode for local development

# Export variables for compose file
export NETWORK_MODE
export IMAGE_NAME
export INSTALL_DEV
export DOCKER_BUILDKIT=1
export COMPOSE_PROJECT_NAME=indexer-local
# Function to show usage
show_help() {
    echo "🚀 Usage: ./local-dev.sh [OPTIONS]"
    echo "Options:"
    echo "  --with-db    Start with local MySQL container"
    echo "  --bridge     Use bridge networking instead of host"
    echo "  --detach     Run containers in the background"
    echo "  --build      Force rebuild of images"
    echo "  --test       Run tests only"
    echo "  --cleanup    Clean up all Docker resources"
    echo "  --image      Set custom image name (default: ${IMAGE_NAME})"
    echo "  -h, --help   Show this help message"
}

# Cleanup function
cleanup_local() {
    echo "🧹 Cleaning up local development environment..."
    echo "  🔄 Stopping containers and removing resources..."
    if docker compose --env-file .env.local -f docker-compose.local.yml down --rmi all -v --remove-orphans; then
        echo "    ✅ Containers and volumes removed"
    else
        echo "    ⚠️  Warning: Issue removing containers and volumes"
    fi

    echo "  🗑️  Removing local development image..."
    if docker rmi ${IMAGE_NAME} --force 2>/dev/null; then
        echo "    ✅ Development image removed"
    else
        echo "    ⚠️  Note: No development image found to remove"
    fi

    # Final cleanup of any dangling resources
    echo "  🧹 Cleaning up dangling resources..."
    docker system prune -f > /dev/null 2>&1

    echo "✨ Cleanup complete"
}

# Trap errors
trap 'error_handler $?' ERR EXIT

# Error handler function
error_handler() {
    local exit_code=$1
    # Skip if exit code is 0 (normal exit)
    if [ "$exit_code" -eq 0 ]; then
        return
    fi

    echo "❌ Error occurred with exit code: $exit_code"
    
    # Get container logs if available
    if [ -n "${CONTAINER_NAME}" ] && docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "📋 Container logs:"
        docker logs ${CONTAINER_NAME}
    fi

    case $exit_code in
        1) echo "   Container failed to start" ;;
        130) 
            if [[ $COMPOSE_OPTS =~ "--detach" ]]; then
                echo "✨ Container is still running in the background"
                exit 0
            fi
            echo "   Script interrupted by user" 
            ;;
        137) echo "   Container received SIGKILL" ;;
        143) echo "   Container received SIGTERM" ;;
        *) echo "   Unknown error occurred" ;;
    esac

    echo "🧹 Running cleanup..."
    cleanup_local
    exit $exit_code
}

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --with-db) PROFILES="--profile with-db"; shift ;;
        --bridge) NETWORK_MODE="bridge"; shift ;;
        --detach|-d) COMPOSE_OPTS="$COMPOSE_OPTS --detach"; shift ;;
        --build) COMPOSE_OPTS="$COMPOSE_OPTS --build"; shift ;;
        --test) RUN_TESTS=true; shift ;;
        --cleanup) CLEANUP=true; shift ;;
        --image) IMAGE_NAME="$2"; shift 2 ;;
        -h|--help) show_help; exit 0 ;;
        *) echo "Unknown parameter: $1"; show_help; exit 1 ;;
    esac
done

# Run cleanup if requested
if [ "$CLEANUP" = true ]; then
    cleanup_local
    exit 0
fi

# Run tests if requested
if [ "$RUN_TESTS" = true ]; then
    ./test-local.sh
    exit $?
fi

# Export network mode for compose file
export NETWORK_MODE

# Export image name for compose file
export IMAGE_NAME

# Function to check container status
check_container_status() {
    local container_name="indexer-local-indexer-1"
    local max_attempts=30
    local attempt=1

    echo "🔍 Checking container status..."
    while [ $attempt -le $max_attempts ]; do
        if docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
            echo "✅ Container ${container_name} is running"
            echo "📋 Following container logs (Press Ctrl+C to detach and leave container running)..."
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            # Trap Ctrl+C to prevent container cleanup
            trap 'echo "✨ Container is still running in the background"; exit 0' INT
            docker logs -f ${container_name}
            return 0
        fi

        if docker ps -a --format '{{.Names}} {{.Status}}' | grep "^${container_name}" | grep -q "Exited"; then
            echo "❌ Container ${container_name} has exited"
            docker logs ${container_name}
            return 1
        fi

        echo "⏳ Waiting for container to start (attempt $attempt/$max_attempts)..."
        sleep 1
        attempt=$((attempt + 1))
    done

    echo "❌ Container failed to start after $max_attempts attempts"
    return 1
}

# Run docker compose with appropriate options
echo "🚀 Starting containers..."

# Debug: Show environment file contents
if [ "$DEBUG" = "1" ]; then
    echo "📄 Environment file contents (.env.local):"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    cat .env.local | sed -E 's/(.*PASS(WORD)?=)[^[:space:]]*/\1********/g' \
                   | sed -E 's/(.*TOKEN=)[^[:space:]]*/\1********/g' \
                   | sed -E 's/(.*SECRET.*=)[^[:space:]]*/\1********/g' \
                   | sed -E 's/(.*KEY.*=)[^[:space:]]*/\1********/g'
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔧 Build arguments:"
    echo "  INSTALL_DEV=${INSTALL_DEV}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

set -e  # Exit on error
docker compose --env-file .env.local -f docker-compose.local.yml ${PROFILES} up ${COMPOSE_OPTS}

# After starting the containers, add this validation check
echo "🔍 Validating network configuration..."
CONTAINER_NAME="${COMPOSE_PROJECT_NAME:?'COMPOSE_PROJECT_NAME not set'}-indexer-1"

# Give the container a moment to start
echo "⏳ Waiting for container to start..."
sleep 5

# Check if container exists and is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "❌ Container ${CONTAINER_NAME} is not running"
    echo "📋 Container logs:"
    docker logs ${CONTAINER_NAME} || true
    exit 1
fi

# Validate network mode
NETWORK_MODE=$(docker inspect --format '{{.HostConfig.NetworkMode}}' ${CONTAINER_NAME})
if [ "$NETWORK_MODE" != "host" ] && [ "$NETWORK_MODE" != "bridge" ]; then
    echo "❌ Container is not running in expected network mode. Current mode: ${NETWORK_MODE}"
    exit 1
fi

# If bridge mode was requested, check port mappings
if [ "$NETWORK_MODE" = "bridge" ]; then
    echo "🌉 Running in bridge mode, checking port mappings..."
    docker port ${CONTAINER_NAME}
elif [ "$NETWORK_MODE" = "host" ]; then
    echo "🔗 Running in host mode - container shares host network stack"
    # Optional: Test connection to a local service
    if nc -z localhost 4000 2>/dev/null; then
        echo "  ✓ CP_RPC_URL (port 4000) is accessible"
    else
        echo "  ⚠️  Warning: CP_RPC_URL (port 4000) is not accessible"
    fi
    if nc -z localhost 8332 2>/dev/null; then
        echo "  ✓ Bitcoin RPC (port 8332) is accessible"
    else
        echo "  ⚠️  Warning: Bitcoin RPC (port 8332) is not accessible"
    fi
fi

# If running in detached mode, check container status
if [[ $COMPOSE_OPTS =~ "--detach" ]]; then
    check_container_status || {
        echo "🧹 Container failed to start properly, cleaning up..."
        cleanup_local
        exit 1
    }
fi