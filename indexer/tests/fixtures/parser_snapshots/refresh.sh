#!/usr/bin/env bash
#
# Regenerate parser_snapshots.json from the committed fixture corpus.
#
# Run this ONLY after an intentional, reindex-validated change to the Rust
# parser or its consensus-surface dependencies (bitcoin / pyo3 / hex / rand).
# It rebuilds the byte-exact parser-output baseline that
# tests/test_parser_snapshots.py asserts against. See issue #765.
#
# Usage (from anywhere in the repo):
#     ./indexer/tests/fixtures/parser_snapshots/refresh.sh
#
set -euo pipefail

# indexer/ is three levels up from this script (fixtures/parser_snapshots/ -> tests -> indexer).
INDEXER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$INDEXER_DIR"

# Make `import tests.*` and `import btc_stamps_parser` resolvable the same way CI does.
export PYTHONPATH="${INDEXER_DIR}/src:${INDEXER_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

exec poetry run python -m tests.parser_snapshot_utils "$@"
