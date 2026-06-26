#!/usr/bin/env python3
"""Tier 3 subprocess-per-block reparse runner (issue #770 Option B).

For each block in the curated set (``indexer/snapshots/ci_consensus_hashes.json``)
spawn a fresh ``smoke_parser_validation.py --block N`` subprocess and aggregate
pass/fail. The subprocess boundary gives automatic state isolation between
blocks (module globals, ``cache_manager["stamp"]["counter"]``,
``util.CURRENT_BLOCK_INDEX``, etc. are reborn per block), sidestepping the
in-process state-carry problem documented in #775.

## Tier 3 scope (cross-block-ledger blocks excluded by design)

This DB-free in-memory runner validates the consensus hashes of blocks whose
result depends only on the block itself. Some baseline blocks additionally
depend on **cross-block SRC-20 ledger state** (prior balances / mint totals /
deploys) to compute ``ledger_hash`` — that state lives in the production
database, which this runner deliberately does not use. Those blocks are listed
in ``TIER3_CROSS_BLOCK_LEDGER`` and excluded here **by design, not because they
are broken**: they are still covered by the Tier 1 (checkpoint cross-check) and
Tier 2 (block-bytes) steps, and their SRC-20 ledger consensus is owned by the
periodic full stampsdev reindex. See #775 / #778.

A block leaves the exclusion set only when it can be validated with no
cross-block state — e.g. when a harness fix makes it self-contained (block
788042 was removed this way in #806). Add or drop entries accordingly.

Pass ``--include-cross-block`` to run the full baseline anyway (these blocks are
expected to mismatch on ``ledger_hash`` without a seeded database — useful for
auditing, not a pass/fail gate).

Usage::

    python3 indexer/ci/ci_reparse_subprocess.py \\
        --baseline indexer/snapshots/ci_consensus_hashes.json

    # Run only N for quick local iteration
    python3 indexer/ci/ci_reparse_subprocess.py --limit 5

    # Audit the full baseline, including the cross-block-ledger blocks
    python3 indexer/ci/ci_reparse_subprocess.py --include-cross-block

    # JSON for downstream tooling
    python3 indexer/ci/ci_reparse_subprocess.py --json > results.json

Exit codes: 0 = all selected blocks pass, 1 = any fail, 2 = config error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Dict, List, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BASELINE = os.path.normpath(os.path.join(HERE, "..", "snapshots", "ci_consensus_hashes.json"))

# Per-block subprocess timeout. Rust parser init + Bitcoin fetch + CP fetch
# for a stamp-heavy block runs ~5-15s on warm cache. 120s is generous and
# still catches truly stuck runs.
DEFAULT_PER_BLOCK_TIMEOUT = 120

# Baseline blocks whose `ledger_hash` depends on cross-block SRC-20 ledger
# state (prior balances / mint totals / deploys) that only the production
# database holds. This in-memory, DB-free runner cannot reproduce that state,
# so these blocks are EXCLUDED FROM TIER 3 BY DESIGN — not because they are
# broken. Coverage for them comes from Tier 1 (checkpoint cross-check) + Tier 2
# (block-bytes), and their SRC-20 ledger consensus from the full reindex (#775).
#
# A 2026-06-26 prototype (real BlockProcessor + MySQL + minimal seed) confirmed
# the shape: ~15/17 reproduce `txlist_hash` correctly but mismatch `ledger_hash`
# without seeded cross-block balances; only blocks with no SRC-20 ledger
# activity pass end-to-end. Retiring the rest would require per-block ledger
# snapshotting (high, ongoing cost) for coverage the reindex already provides —
# so they stay excluded and we grow cheap coverage via #778 instead.
#
# An entry leaves this set only when a block becomes self-contained (e.g. 788042
# was removed in #806 after the genesis+1 harness fix).
TIER3_CROSS_BLOCK_LEDGER: Set[int] = {
    784551,
    789624,
    792369,
    792370,
    792371,
    793068,
    793069,
    795999,
    796001,
    832999,
    833000,
    833001,
    864999,
    870651,
    870652,
    870653,
    872000,
}


def _load_baseline(path: str) -> List[int]:
    """Return the sorted list of block_index values from the curated baseline."""
    with open(path) as fh:
        data = json.load(fh)
    hashes = data.get("hashes")
    if not isinstance(hashes, dict):
        raise SystemExit(f"baseline {path}: 'hashes' is missing or not a dict")
    return sorted(int(k) for k in hashes.keys())


def _run_one(block_index: int, timeout_sec: int) -> Tuple[bool, float, str]:
    """Spawn a single smoke_parser_validation subprocess. Returns
    ``(ok, duration_sec, tail_for_logs)``."""
    smoke_path = os.path.join(HERE, "smoke_parser_validation.py")
    cmd = [sys.executable, smoke_path, "--block", str(block_index)]
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired as e:
        return (False, time.monotonic() - start, f"TIMEOUT after {timeout_sec}s: {e}")
    duration = time.monotonic() - start
    ok = proc.returncode == 0
    parts: List[str] = []
    if proc.stderr:
        parts.append("--- stderr (tail) ---\n" + proc.stderr[-2048:])
    if not ok and proc.stdout:
        parts.append("--- stdout (tail) ---\n" + proc.stdout[-2048:])
    return (ok, duration, "\n".join(parts))


def run(
    blocks: List[int],
    timeout_sec: int,
    fail_fast: bool = False,
    output_json: bool = False,
) -> Tuple[int, List[Dict]]:
    """Run the subprocess runner over ``blocks``. Returns ``(exit_code, results)``."""
    results: List[Dict] = []
    fail_count = 0
    overall_start = time.monotonic()

    for i, block in enumerate(blocks, 1):
        if not output_json:
            print(f"[{i}/{len(blocks)}] block {block}: running...", flush=True)
        ok, duration, tail = _run_one(block, timeout_sec)
        result = {"block": block, "ok": ok, "duration_sec": round(duration, 2)}
        if not ok:
            result["tail"] = tail
            fail_count += 1
        results.append(result)
        if not output_json:
            status = "✓" if ok else "✗"
            print(f"[{i}/{len(blocks)}] block {block}: {status} ({duration:.1f}s)", flush=True)
            if not ok:
                # Surface the failure tail in-line so CI logs are self-contained.
                print(tail, flush=True)
        if fail_fast and not ok:
            if not output_json:
                print(f"\nfail-fast: stopping after first failure (block {block})", flush=True)
            break

    overall_duration = time.monotonic() - overall_start
    if not output_json:
        passed = len(results) - fail_count
        print(
            f"\nSubprocess reparse complete: {passed}/{len(results)} passed, "
            f"{fail_count} failed in {overall_duration:.1f}s"
        )
    return (1 if fail_count else 0, results)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tier 3 subprocess-per-block reparse runner (#770).")
    ap.add_argument("--baseline", default=DEFAULT_BASELINE, help="path to ci_consensus_hashes.json")
    ap.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_PER_BLOCK_TIMEOUT,
        help=f"per-block subprocess timeout in seconds (default: {DEFAULT_PER_BLOCK_TIMEOUT})",
    )
    ap.add_argument("--limit", type=int, default=0, help="if >0, only run the first N blocks after filtering")
    ap.add_argument("--fail-fast", action="store_true", help="stop on first failing block")
    ap.add_argument("--json", action="store_true", help="emit a single JSON summary on stdout instead of per-block lines")
    ap.add_argument(
        "--include-cross-block",
        action="store_true",
        help="also run blocks in TIER3_CROSS_BLOCK_LEDGER (excluded by design; expected to "
        "mismatch ledger_hash without a seeded DB). Default: exclude them.",
    )
    args = ap.parse_args()

    try:
        all_blocks = _load_baseline(args.baseline)
    except (FileNotFoundError, json.JSONDecodeError, SystemExit) as e:
        print(f"ERROR loading baseline: {e}", file=sys.stderr)
        return 2

    if args.include_cross_block:
        blocks = all_blocks
        if not args.json:
            print(f"Including {len(TIER3_CROSS_BLOCK_LEDGER)} cross-block-ledger blocks (audit mode; #775).")
    else:
        blocks = [b for b in all_blocks if b not in TIER3_CROSS_BLOCK_LEDGER]
        if not args.json:
            excluded = len(all_blocks) - len(blocks)
            print(
                f"Excluding {excluded} cross-block-ledger blocks (covered by Tier 1/2 + full reindex; #775). "
                "Use --include-cross-block to audit them."
            )

    if args.limit and args.limit > 0:
        blocks = blocks[: args.limit]

    if not blocks:
        print("ERROR: no blocks selected after filtering", file=sys.stderr)
        return 2

    exit_code, results = run(blocks, args.timeout, fail_fast=args.fail_fast, output_json=args.json)

    if args.json:
        summary = {
            "baseline": args.baseline,
            "excluded_cross_block_ledger": sorted(TIER3_CROSS_BLOCK_LEDGER) if not args.include_cross_block else [],
            "total_run": len(results),
            "passed": sum(1 for r in results if r["ok"]),
            "failed": sum(1 for r in results if not r["ok"]),
            "results": results,
        }
        print(json.dumps(summary, indent=2))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
