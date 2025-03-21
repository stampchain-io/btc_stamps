#!/bin/bash

# Bitcoin Stamps Indexer Container Runner
# A unified script for running both development and production containers
# Usage: ./run-container.sh [OPTIONS]
# Examples:
#   Development: ./run-container.sh --build         # Build and run local dev image
#   Production:  ./run-container.sh --image latest  # Run latest from Docker Hub

# Set up environment
cd "$(dirname "$0")"
SCRIPT_DIR=$(realpath "$(pwd)")
LOGS_DIR="${SCRIPT_DIR}/logs"

# Default values
PROFILES=""
NETWORK_MODE="host"
COMPOSE_OPTS=""
CLEANUP=false
TEST_ONLY=false
IMAGE_SOURCE="local"  # local, hub, custom
IMAGE_NAME="btcstamps/indexer:local-dev"  # Default for local development
DOCKER_HUB_VERSION=""
CUSTOM_IMAGE=""
ENV_FILE=".env.local"
DEV_MODE="true"
LOG_MODE="local"  # local or container

# Function to show usage
show_help() {
    echo "🚀 Bitcoin Stamps Indexer Container Runner"
    echo "Usage: ./run-container.sh [OPTIONS]"
    echo ""
    echo "Environment options:"
    echo "  --dev              Development mode (default): logs to local files"
    echo "  --prod             Production mode: logs to stdout/stderr (better for debugging)"
    echo "  --env-file FILE    Use custom env file (default: .env.local)"
    echo ""
    echo "Image options (choose one):"
    echo "  --build            Build local development image (default)"
    echo "  --image VERSION    Pull specific version from Docker Hub (e.g., latest, dev, 1.8.26)"
    echo "  --custom-image IMG Use a custom Docker image"
    echo ""
    echo "Network options:"
    echo "  --with-db          Start with local MySQL container"
    echo "  --bridge           Use bridge networking instead of host"
    echo ""
    echo "Runtime options:"
    echo "  --detach, -d       Run container in background"
    echo "  --cleanup          Clean up all Docker resources and exit"
    echo "  --test             Test Docker build and run without starting services"
    echo "  -h, --help         Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./run-container.sh --build                # Build and run local dev image"
    echo "  ./run-container.sh --image latest         # Run latest from Docker Hub"
    echo "  ./run-container.sh --image dev --prod     # Run dev version with stdout logs (best for testing)"
    echo "  ./run-container.sh --image 1.8.26 --prod  # Run specific version in prod mode"
    echo "  ./run-container.sh --custom-image my/img  # Run custom image"
    echo "  ./run-container.sh --cleanup              # Clean up resources"
    echo ""
    echo "Database connections:"
    echo "  All modes connect to the MySQL server defined in your .env.local file or specified env file."
    echo "  For local development with MySQL, ensure your database is running and accessible."
}

# Cleanup function
cleanup_resources() {
    echo "🧹 Cleaning up Docker resources..."
    echo "  🔄 Stopping containers and removing resources..."
    if docker compose --env-file "$ENV_FILE" -f docker-compose.local.yml down --rmi all -v --remove-orphans; then
        echo "    ✅ Containers and volumes removed"
    else
        echo "    ⚠️  Warning: Issue removing containers and volumes"
    fi

    echo "  🗑️  Removing development images..."
    if docker rmi btcstamps/indexer:local-dev --force 2>/dev/null; then
        echo "    ✅ Development image removed"
    else
        echo "    ⚠️  Note: No development image found to remove"
    fi

    # Final cleanup of any dangling resources
    echo "  🧹 Cleaning up dangling resources..."
    docker system prune -f > /dev/null 2>&1

    echo "✨ Cleanup complete"
}

# Test Docker build and run
test_docker_build() {
    echo "🧪 Testing Docker build and run..."
    
    # Clean up any previous test resources
    cleanup_resources
    
    # Build the image
    echo "  🔨 Building test image..."
    if ! docker build -t btcstamps/indexer:test-build ./; then
        echo "  ❌ Docker build failed!"
        return 1
    fi
    echo "  ✅ Docker build successful"
    
    # Test running the container briefly
    echo "  🚀 Testing container startup..."
    if ! timeout 10 docker run --rm btcstamps/indexer:test-build poetry --version; then
        echo "  ❌ Container test failed!"
        return 1
    fi
    echo "  ✅ Container starts successfully"
    
    # Clean up
    docker rmi btcstamps/indexer:test-build --force
    
    echo "🎉 Docker build and run test passed!"
    return 0
}

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        # Environment options
        --dev) DEV_MODE="true"; LOG_MODE="local"; shift ;;
        --prod) DEV_MODE="false"; LOG_MODE="container"; shift ;;
        --env-file) ENV_FILE="$2"; shift 2 ;;
        
        # Image options
        --build) IMAGE_SOURCE="local"; COMPOSE_OPTS="$COMPOSE_OPTS --build"; shift ;;
        --image) IMAGE_SOURCE="hub"; DOCKER_HUB_VERSION="$2"; shift 2 ;;
        --custom-image) IMAGE_SOURCE="custom"; CUSTOM_IMAGE="$2"; shift 2 ;;
        
        # Network options
        --with-db) PROFILES="--profile with-db"; shift ;;
        --bridge) NETWORK_MODE="bridge"; shift ;;
        
        # Runtime options
        --detach|-d) COMPOSE_OPTS="$COMPOSE_OPTS --detach"; shift ;;
        --cleanup) CLEANUP=true; shift ;;
        --test) TEST_ONLY=true; shift ;;
        -h|--help) show_help; exit 0 ;;
        
        # Unknown option
        *) echo "❌ Unknown parameter: $1"; show_help; exit 1 ;;
    esac
done

# Handle cleanup request
if [ "$CLEANUP" = true ]; then
    cleanup_resources
    exit 0
fi

# Ensure environment file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: Environment file $ENV_FILE does not exist"
    exit 1
fi

# Configure image based on source
case $IMAGE_SOURCE in
    "local")
        IMAGE_NAME="btcstamps/indexer:local-dev"
        export MOUNT_CODE_DIR="."
        export CONTAINER_COMMAND=""
        echo "🏗️ Using local development image: $IMAGE_NAME"
        ;;
    "hub")
        if [ -z "$DOCKER_HUB_VERSION" ]; then
            echo "❌ Error: No version specified for Docker Hub image"
            exit 1
        fi
        IMAGE_NAME="btcstamps/indexer:$DOCKER_HUB_VERSION"
        # Try to pull the image
        echo "🔄 Pulling $IMAGE_NAME from Docker Hub..."
        if ! docker pull "$IMAGE_NAME"; then
            echo "❌ Failed to pull image $IMAGE_NAME"
            exit 1
        fi
        echo "✅ Successfully pulled image"
        # Skip build step by removing --build if present
        COMPOSE_OPTS=$(echo "$COMPOSE_OPTS" | sed 's/--build//')
        # Don't mount code directory when using pulled image
        export MOUNT_CODE_DIR=""
        # Set command to use poetry run indexer directly (no supervisord)
        export CONTAINER_COMMAND="poetry run indexer"
        # Add environment variables to help with OpenSSL issues
        export ADDITIONAL_ENV="PYTHONPATH=/app:/app/src:$PYTHONPATH LD_LIBRARY_PATH=/usr/lib:/usr/local/lib"
        ;;
    "custom")
        if [ -z "$CUSTOM_IMAGE" ]; then
            echo "❌ Error: No custom image specified"
            exit 1
        fi
        IMAGE_NAME="$CUSTOM_IMAGE"
        # Skip build step by removing --build if present
        COMPOSE_OPTS=$(echo "$COMPOSE_OPTS" | sed 's/--build//')
        # Don't mount code directory when using custom image
        export MOUNT_CODE_DIR=""
        echo "🔄 Using custom image: $IMAGE_NAME"
        # Set command to use poetry run indexer directly (no supervisord)
        export CONTAINER_COMMAND="poetry run indexer"
        # Add environment variables to help with OpenSSL issues
        export ADDITIONAL_ENV="PYTHONPATH=/app:/app/src:$PYTHONPATH LD_LIBRARY_PATH=/usr/lib:/usr/local/lib"
        ;;
esac

# Create needed directories based on log mode
if [ "$LOG_MODE" = "local" ]; then
    # For development with local logs
    mkdir -p "${LOGS_DIR}"
    chmod -R 777 "${LOGS_DIR}"
else
    # For production mode - log to stdout/stderr
    # Create a temporary env file with PYTHONUNBUFFERED set
    echo "# Temporary environment file with PYTHONUNBUFFERED set" > .env.tmp
    echo "PYTHONUNBUFFERED=1" >> .env.tmp
    cat "$ENV_FILE" >> .env.tmp
    ENV_FILE=".env.tmp"
fi

# Handle test-only mode
if [ "$TEST_ONLY" = true ]; then
    echo "🧪 Running Docker build and run tests only..."
    if test_docker_build; then
        echo "✅ All tests passed successfully"
        exit 0
    else
        echo "❌ Tests failed"
        exit 1
    fi
fi

# Export variables for compose file
export NETWORK_MODE
export IMAGE_NAME
export INSTALL_DEV="$DEV_MODE"

echo "🚀 Running container with image: $IMAGE_NAME"
echo "  • Network mode: $NETWORK_MODE"
echo "  • Environment: $([ "$DEV_MODE" = "true" ] && echo "Development" || echo "Production")"
echo "  • Logging: $([ "$LOG_MODE" = "local" ] && echo "Local files" || echo "Container stdout/stderr")"
echo "  • Environment file: $ENV_FILE"

# Run the container
set -e  # Exit on error
docker compose --env-file "$ENV_FILE" -f docker-compose.local.yml $PROFILES up $COMPOSE_OPTS

# If temporary env file was created, remove it
if [ "$ENV_FILE" = ".env.tmp" ]; then
    rm -f .env.tmp
fi

# Handle detached mode feedback
if [[ $COMPOSE_OPTS =~ "--detach" ]]; then
    echo "✅ Container started in detached mode"
    echo "📋 To view logs: docker logs indexer-local-indexer-1 -f"
    echo "🛑 To stop: docker compose --env-file $ENV_FILE -f docker-compose.local.yml down"
fi 