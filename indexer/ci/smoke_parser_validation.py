#!/usr/bin/env python3
"""Exploratory smoke test for the public-endpoint reparse path.

Goal: confirm that ``index_core.reparse.validator.ReparseValidator.validate_block``
can be driven end-to-end via the PublicNodeBackend shim (blockstream.info for
Bitcoin) and the public ``api.counterparty.io:4000`` endpoint for Counterparty
data, against ONE consensus boundary block, with no sparky-side bitcoind or
CP-core access needed.

If this works for one block, the next iteration scales to all 38 fixtures in
``indexer/snapshots/ci_consensus_hashes.json`` and wires the runner into the
``reparse-validate`` workflow.

If this breaks (likely failure modes: missing backend methods uncovered by
process_tx -> list_tx, CP API rate-limiting, schema mismatch on
ci_consensus_hashes.json), surface the gap explicitly so we can decide
between (a) extending PublicNodeBackend, (b) using a configured private RPC
secret instead, or (c) falling back to a parser-smoke-only check.

Usage:
    poetry run python indexer/ci/smoke_parser_validation.py --block 779652
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Force test/mock-DB mode before any index_core imports so config + DB layers
# don't try to attach to a real MySQL.
os.environ.setdefault("USE_TEST_DB", "1")
os.environ.setdefault("MOCK_DB", "1")
os.environ.setdefault("TESTING", "1")
# Point Counterparty fetcher at the public endpoint so we don't need a local
# CP-core. The reparse validator reads CP data via fetch_xcp_blocks_concurrent
# which honours these env vars.
os.environ.setdefault("CP_PRIMARY_NODE_URL", "https://api.counterparty.io:4000")
os.environ.setdefault("CP_FALLBACK_NODE_URL", "https://api.counterparty.io:4000")

# Push the indexer/ci dir on path so we can import public_backend, and
# indexer/src so we can import index_core directly (mirrors how poetry's
# editable install lays out the package).
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "src"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", type=int, required=True, help="block index to validate")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Install the public-endpoint backend override BEFORE importing index_core
    # modules, so their import-time ``backend_instance = Backend()`` globals pick
    # it up through the production injection seam (no monkey-patching, no
    # import-order fragility). Doing this inside main() — rather than mutating
    # os.environ at module import — keeps importing this module side-effect-free,
    # so unit tests can import it without polluting Backend() for the suite.
    from public_backend import install_public_backend  # type: ignore

    backend = install_public_backend()
    print(f"Installed PublicNodeBackend ({backend.base}) for block {args.block}")

    from index_core.reparse.validator import ReparseValidator

    # Resolve the snapshot path relative to this script so it works regardless
    # of caller cwd.
    snapshot_path = os.path.normpath(os.path.join(HERE, "..", "snapshots", "reference_hashes.json"))
    validator = ReparseValidator(snapshot_path=snapshot_path)
    ok = validator.validate_block(args.block)
    print(f"validate_block({args.block}) = {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
