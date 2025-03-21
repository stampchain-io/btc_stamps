#!/bin/bash

# Legacy wrapper script for backward compatibility
# This script is maintained for backward compatibility with existing workflows.
# It delegates to the new unified run-container.sh script.

cd "$(dirname "$0")"

echo "ℹ️ Running Bitcoin Stamps Indexer using new unified container runner..."
echo "ℹ️ For more options, try: ./run-container.sh --help"
echo ""

# Map old arguments to new ones
ARGS=""
PULL_VERSION=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --with-db) ARGS="$ARGS --with-db"; shift ;;
        --bridge) ARGS="$ARGS --bridge"; shift ;;
        --detach|-d) ARGS="$ARGS --detach"; shift ;;
        --build) ARGS="$ARGS --build"; shift ;;
        --test) exec ./test-local.sh; shift ;;
        --cleanup) ARGS="$ARGS --cleanup"; shift ;;
        --image) PULL_VERSION="$2"; shift 2 ;;
        --pull) PULL_VERSION="$2"; shift 2 ;;
        -h|--help) ./run-container.sh --help; exit 0 ;;
        *) echo "Unknown parameter: $1"; ./run-container.sh --help; exit 1 ;;
    esac
done

# If a version was specified to pull, use the --image option
if [ -n "$PULL_VERSION" ]; then
    ARGS="$ARGS --image $PULL_VERSION"
else
    # Default is to build the local development image
    ARGS="$ARGS --build"
fi

# Run the new script with the mapped arguments
exec ./run-container.sh $ARGS