#!/bin/bash

# DEPRECATED: This script is deprecated and will be removed in a future version.
# Please use ./run-container.sh instead.
# Example: ./run-container.sh --image latest
# See ./run-container.sh --help for more options

echo "⚠️  WARNING: run-image.sh is deprecated and will be removed in a future version."
echo "Please use ./run-container.sh instead."
echo "Example: ./run-container.sh --image latest"
echo "See ./run-container.sh --help for more options"
echo ""
echo "Redirecting to run-container.sh..."
echo ""

# Extract the image name
if [ -z "$1" ]; then
    echo "❌ Error: Docker image is required"
    echo "Usage: ./run-container.sh --image TAG"
    exit 1
fi

IMAGE_NAME="$1"
shift

# Map arguments to new script format
ARGS="--custom-image $IMAGE_NAME"

# Parse and map remaining arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --with-db) ARGS="$ARGS --with-db"; shift ;;
        --bridge) ARGS="$ARGS --bridge"; shift ;;
        --detach|-d) ARGS="$ARGS --detach"; shift ;;
        --env-file) ARGS="$ARGS --env-file $2"; shift 2 ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
done

# Add prod mode for better compatibility
ARGS="$ARGS --prod"

# Execute the new script with mapped arguments
exec ./run-container.sh $ARGS