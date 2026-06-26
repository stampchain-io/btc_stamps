#!/usr/bin/env python3
"""Run the reparse pipeline against every curated boundary block (#770).

This is the multi-block extension of indexer/ci/smoke_parser_validation.py
that #769 delivered. Where the smoke driver validates ONE block, this runner
validates every entry in indexer/snapshots/ci_consensus_hashes.json — the
curated set of consensus-boundary blocks (see refresh-consensus-hashes.sh
for the source list).

Curated subsets are NON-contiguous — block N + 1 is often missing — so the
validator's normal chain-position lookup (snapshot_manager.get_expected_hash
of block N - 1) falls back to all-zeros for any block where the prior block
isn't in reference_hashes.json. That makes messages_hash deterministically
wrong even when the block's own contents are fine.

Tier 1 fix: refresh-consensus-hashes.sh now records prev_block_hash,
prev_messages_hash, prev_txlist_hash, prev_ledger_hash per entry, sourced
from reference_hashes.json or prod RDS. Before each validate_block(N) call
this runner stitches the prev-hashes entry into the validator's in-memory
snapshot as a synthetic N - 1 row, so the chain-position lookup succeeds
without needing reference_hashes.json to cover N - 1.

The runner still seeds reparse_caching.cache_manager['stamp']['counter']
from stamp_counter_before, populated by the refresh script from prod RDS.
The remaining txlist_hash failures (see #775) are structural divergences
between InMemoryBlockProcessor and the production StampProcessor — not
fixable by state seeding. Tier 3 (subprocess-per-block + production
BlockProcessor + seeded mini-DB) is the proper fix for those; this runner
exists to land the messages_hash win cheaply now.

Trust model: identical to smoke_parser_validation.py — Bitcoin blocks are
content-addressed (PublicNodeBackend verifies SHA256 before parsing) and
Counterparty data comes from the public api.counterparty.io:4000 endpoint.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

# Force test/mock-DB mode BEFORE any index_core imports so config + DB layers
# don't try to attach to a real MySQL.
os.environ.setdefault("USE_TEST_DB", "1")
os.environ.setdefault("MOCK_DB", "1")
os.environ.setdefault("TESTING", "1")
# Public CP endpoint — used by reparse.validator via fetch_xcp_blocks_concurrent.
os.environ.setdefault("CP_PRIMARY_NODE_URL", "https://api.counterparty.io:4000")
os.environ.setdefault("CP_FALLBACK_NODE_URL", "https://api.counterparty.io:4000")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "src"))


# Block-scoped caches that are safe to clear between blocks. The validator
# treats them as block-scoped writes; clearing produces the same effect as the
# in-block reset that a from-genesis run does at the start of each block.
_RESET_CACHES = (
    "total_minted",
    "balance",
    "collection",
    "src101_deploy",
    "deploy",
    "subasset",
    "price",
    "address",
    "market_data",
    "block",
    "reissue",
)


def seed_cache_for_block(seed_counter: int) -> None:
    """Prepare cache_manager state so validate_block(N) computes correct hashes."""
    import index_core.caching as reparse_caching

    cm = reparse_caching.cache_manager
    for name in _RESET_CACHES:
        cache = cm.get_cache(name)
        if cache is not None:
            cache.clear()
    cm.set_cache_value("stamp", "counter", seed_counter)


def stitch_prev_anchor(ref_hashes: dict, block_index: int, entry: dict) -> bool:
    """Inject a synthetic block_index-1 entry built from the curated prev-hash
    fields so SnapshotManager.get_expected_hash(block_index - 1) succeeds even
    when reference_hashes.json doesn't cover the prior block.

    Returns True if a prev anchor was stitched in, False if the curated entry
    didn't carry prev-hash fields (e.g. genesis) or the prior block was already
    present in ref_hashes.
    """
    prev_index = block_index - 1
    if str(prev_index) in ref_hashes:
        return False
    prev_hash = entry.get("prev_block_hash")
    if not prev_hash:
        return False
    ref_hashes[str(prev_index)] = {
        "block_hash": prev_hash,
        "ledger_hash": entry.get("prev_ledger_hash", ""),
        "txlist_hash": entry.get("prev_txlist_hash", ""),
        "messages_hash": entry.get("prev_messages_hash", ""),
    }
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--ci-baseline",
        default=os.path.join(HERE, "..", "snapshots", "ci_consensus_hashes.json"),
        help="curated CI baseline (per-block stamp_counter_before + prev-hash fields)",
    )
    ap.add_argument(
        "--reference",
        default=os.path.join(HERE, "..", "snapshots", "reference_hashes.json"),
        help="canonical reference baseline (chain provider for prev-hash lookup)",
    )
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="run every block even after a failure (default: stop on first)",
    )
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Install the public-endpoint backend override BEFORE importing index_core
    # modules, so their import-time ``backend_instance = Backend()`` globals pick
    # it up through the production injection seam (no monkey-patching, no
    # import-order fragility). Doing this inside main() — rather than mutating
    # os.environ at module import — keeps importing this module side-effect-free,
    # so unit tests (test_ci_reparse_multi) can import it without polluting
    # Backend() for the rest of the suite.
    from public_backend import install_public_backend  # type: ignore

    backend = install_public_backend()
    print(f"PublicNodeBackend installed ({backend.base})")

    from index_core.reparse.validator import ReparseValidator

    with open(args.ci_baseline) as f:
        ci_baseline = json.load(f)
    targets = ci_baseline.get("hashes") or ci_baseline.get("blocks") or {}
    if not targets:
        print(f"::error::{args.ci_baseline} has no 'hashes' or 'blocks' key", file=sys.stderr)
        return 1

    validator = ReparseValidator(snapshot_path=os.path.normpath(args.reference))
    ref_hashes = validator.snapshot_manager.load_snapshot().get("hashes", {})

    # Stitch each curated block's own entry into the snapshot (so the validator
    # can look up the expected hash for the block under test), then stitch a
    # synthetic block_index-1 anchor from the prev-hash fields so the chain
    # walk succeeds even when reference_hashes.json doesn't cover the prior
    # block.
    self_merged = prev_merged = 0
    for k, entry in targets.items():
        if k not in ref_hashes:
            ref_hashes[k] = {
                "block_hash": entry["block_hash"],
                "ledger_hash": entry.get("ledger_hash", ""),
                "txlist_hash": entry.get("txlist_hash", ""),
                "messages_hash": entry.get("messages_hash", ""),
            }
            self_merged += 1
        if stitch_prev_anchor(ref_hashes, int(k), entry):
            prev_merged += 1
    if self_merged or prev_merged:
        print(f"Merged {self_merged} curated entries + {prev_merged} prev anchors into the validator snapshot")

    block_indices = sorted(int(b) for b in targets)
    print(f"Validating {len(block_indices)} curated blocks via reparse pipeline\n")

    passed = failed = 0
    for block_index in block_indices:
        entry = targets[str(block_index)]
        reason = entry.get("reason", "")
        seed_counter = int(entry.get("stamp_counter_before", 0))
        seed_cache_for_block(seed_counter)
        try:
            ok = validator.validate_block(block_index)
        except Exception as e:
            print(f"  block {block_index} ({reason}): EXCEPTION — {e}")
            failed += 1
            if not args.continue_on_failure:
                break
            continue
        if ok:
            print(f"  block {block_index} ({reason}): OK [seed={seed_counter}]")
            passed += 1
        else:
            print(f"  block {block_index} ({reason}): MISMATCH [seed={seed_counter}]")
            failed += 1
            if not args.continue_on_failure:
                break

    print()
    print(f"Summary: {passed} passed, {failed} failed (of {len(block_indices)} total)")
    if failed:
        print("::error::reparse consensus validation failed", file=sys.stderr)
        return 1
    print("All curated blocks validated cleanly via the reparse pipeline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
