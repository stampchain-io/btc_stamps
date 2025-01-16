#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Cleanup function
cleanup() {
    echo "Cleaning up..."
    local cleanup_exit_code=0

    echo "  • Stopping containers..."
    if docker compose --env-file .env.docker -f docker-compose.test.yml down --timeout 5; then
        echo "    ✔ Containers stopped"
    else
        echo "    ⚠️  Warning: Issue stopping containers"
        cleanup_exit_code=1
    fi

    echo "  • Removing test image..."
    if docker rmi btc_stamps/indexer:test --force; then
        echo "    ✔ Test image removed"
    else
        echo "    ⚠️  Warning: Could not remove test image"
        cleanup_exit_code=1
    fi

    echo "  • Removing test files..."
    if rm -f .env.docker docker-compose.test.yml; then
        echo "    ✔ Test files removed"
    else
        echo "    ⚠️  Warning: Issue removing test files"
        cleanup_exit_code=1
    fi

    # Final cleanup of any dangling resources
    echo "  • Cleaning up dangling resources..."
    docker system prune -f > /dev/null 2>&1

    if [ $cleanup_exit_code -eq 0 ]; then
        echo "Cleanup complete"
    else
        echo "⚠️  Cleanup completed with warnings"
    fi
}

# Set up cleanup trap
trap cleanup EXIT

echo "🚀 Starting local test simulation..."

# Ensure we're in the correct directory and set up paths
cd "$(dirname "$0")"
SCRIPT_DIR="$(pwd)"
export PWD="${SCRIPT_DIR}"
LOGS_DIR="${SCRIPT_DIR}/logs"
FILES_DIR="${SCRIPT_DIR}/../files"

# Create environment file for Docker Compose
echo "Creating Docker environment file..."
cat > .env.docker << EOL
PWD=${SCRIPT_DIR}
COMPOSE_PROJECT_DIR=${SCRIPT_DIR}
COMPOSE_PROJECT_NAME=indexer-test
DOCKER_BUILDKIT=1
COMPOSE_DOCKER_CLI_BUILD=1
COMPOSE_IGNORE_ORPHANS=true
DOCKER_CONTAINER=1
PYTHONUNBUFFERED=1
DEBUG=1
EOL

# Create test docker-compose file
cat > docker-compose.test.yml << EOL
services:
  indexer:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        PYTHON_VERSION: 3.12
    image: btc_stamps/indexer:test
    labels:
      com.docker.compose.project: indexer-test
    working_dir: /app
    env_file:
      - .env.docker
    volumes:
      - ${LOGS_DIR}:/app/logs
      - ${FILES_DIR}:/usr/src/app/files
    user: root
    command: >
      sh -c "poetry install &&
             chown -R indexer:indexer /usr/local/lib/python3.12/site-packages &&
             su indexer -c 'poetry run python -c \"import start; start.test_setup()\"'"
EOL

# Ensure entrypoint script exists and is executable
if [ ! -f docker-entrypoint.sh ]; then
    echo "Creating docker-entrypoint.sh..."
    cat > docker-entrypoint.sh << 'EOL'
#!/bin/bash
set -e

# Create logs directory if not using Docker container logging
if [ "$DOCKER_CONTAINER" != "1" ]; then
    mkdir -p /app/logs
    chown indexer:indexer /app/logs
fi

# Execute the main command
exec "$@"
EOL
    chmod +x docker-entrypoint.sh
fi

# Build and run tests
echo "📦 Building and running tests..."
if docker compose --env-file .env.docker -f docker-compose.test.yml up --build  --exit-code-from indexer; then
    echo -e "${GREEN}✅ Tests passed${NC}"
    EXIT_CODE=0
else
    echo -e "${RED}❌ Tests failed${NC}"
    EXIT_CODE=1
fi

exit $EXIT_CODE 