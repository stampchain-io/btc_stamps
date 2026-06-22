#!/usr/bin/env bash
# Build the production indexer image and dump its resolved pip freeze
# into indexer/ci/freeze.prod.lock. The output is the baseline that
# .github/workflows/freeze-drift.yml diffs against on every PR.
#
# Run this whenever you intentionally change pyproject.toml, poetry.lock,
# or indexer/Dockerfile and commit the updated baseline in the same PR.
#
# Usage:
#   ./indexer/ci/refresh-freeze.sh
#   # then: git add indexer/ci/freeze.prod.lock && git commit
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

IMAGE_TAG="btc-stamps-freeze-baseline:tmp"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
OUTPUT="indexer/ci/freeze.prod.lock"

echo "Building production-mode image (Python $PYTHON_VERSION, INSTALL_DEV=false)..."
docker build \
  --build-arg "PYTHON_VERSION=$PYTHON_VERSION" \
  --build-arg "INSTALL_DEV=false" \
  --target builder \
  -t "$IMAGE_TAG" \
  -f indexer/Dockerfile \
  indexer

echo "Dumping resolved pip freeze from container..."
# --exclude-editable skips the indexer itself (installed as -e /app); we only
# want to track third-party version drift, not our own canary version bumps.
docker run --rm "$IMAGE_TAG" pip freeze --all --exclude-editable \
  | LC_ALL=C sort > "$OUTPUT"

echo "Wrote $OUTPUT ($(wc -l < "$OUTPUT") lines)"
echo "Review with: git diff $OUTPUT"
