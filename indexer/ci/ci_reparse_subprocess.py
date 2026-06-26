#!/usr/bin/env python3
"""Tier 3 subprocess-per-block reparse runner (issue #770 Option B).

For each block in the curated set (``indexer/snapshots/ci_consensus_hashes.json``)
spawn a fresh ``smoke_parser_validation.py --block N`` subprocess and aggregate
pass/fail. The subprocess boundary gives automatic state isolation between
blocks (module globals, ``cache_manager["stamp"]["counter"]``,
``util.CURRENT_BLOCK_INDEX``, etc. are reborn per block), sidestepping the
in-process state-carry problem documented in #775.

## Known-failing blocks (skipped by default)

The 38-block baseline includes blocks that fail in the in-memory reparse
validator due to ``InMemoryBlockProcessor`` structural divergence from the
production ``StampProcessor`` (#775). Those failures aren't fixable here —
subprocess isolation can't paper over a processor-implementation gap. They
are listed in ``TIER3_KNOWN_FAILURES`` and skipped by default so Tier 3
gives clean per-PR signal on the blocks it CAN validate.

As individual #775 sub-bugs land, remove the relevant block_index from
``TIER3_KNOWN_FAILURES`` so Tier 3 picks them up automatically.

Pass ``--include-known-failures`` to run the full baseline (useful for
auditing how many #775 blockers remain after a fix).

Usage::

    python3 indexer/ci/ci_reparse_subprocess.py \\
        --baseline indexer/snapshots/ci_consensus_hashes.json

    # Run only N for quick local iteration
    python3 indexer/ci/ci_reparse_subprocess.py --limit 5

    # Audit the full 38, including the #775-blocked ones
    python3 indexer/ci/ci_reparse_subprocess.py --include-known-failures

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

# Blocks in the curated baseline that currently fail in the in-memory
# reparse validator due to #775's `InMemoryBlockProcessor` divergences from
# the production `StampProcessor`. They are not fixable in this runner;
# the underlying processor needs to be aligned with production. Skipping
# them keeps Tier 3 actionable as a per-PR signal on the blocks it CAN
# validate. Remove entries as #775 sub-bugs land.
#
# Origin: empirical run of the full baseline on 2026-06-24 against dev tip,
# 18 of 38 blocks failed (16 `'bytes' object has no attribute 'get'` errors
# from OLGA payload extraction + 1 `ConsensusError` at block 788042 + 1
# generic InMemoryBlockProcessor crash). See #775.
#
# 2026-06-26: block 788042 (the `ConsensusError`) fixed — the validator now
# mirrors production by treating the previous ledger hash as unset at SRC-20
# genesis+1 (validator.compute_block_hashes). It validates cleanly and was
# removed from this list. 17 known failures remain (all `InMemoryBlockProcessor`
# divergences tracked by #775).
TIER3_KNOWN_FAILURES: Set[int] = {
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
        "--include-known-failures",
        action="store_true",
        help="include blocks listed in TIER3_KNOWN_FAILURES (#775-blocked). Default: skip them.",
    )
    args = ap.parse_args()

    try:
        all_blocks = _load_baseline(args.baseline)
    except (FileNotFoundError, json.JSONDecodeError, SystemExit) as e:
        print(f"ERROR loading baseline: {e}", file=sys.stderr)
        return 2

    if args.include_known_failures:
        blocks = all_blocks
        if not args.json:
            print(f"Including {len(TIER3_KNOWN_FAILURES)} known-failing blocks (#775).")
    else:
        blocks = [b for b in all_blocks if b not in TIER3_KNOWN_FAILURES]
        if not args.json:
            skipped = len(all_blocks) - len(blocks)
            print(f"Skipping {skipped} known-failing blocks (#775). Use --include-known-failures to run them too.")

    if args.limit and args.limit > 0:
        blocks = blocks[: args.limit]

    if not blocks:
        print("ERROR: no blocks selected after filtering", file=sys.stderr)
        return 2

    exit_code, results = run(blocks, args.timeout, fail_fast=args.fail_fast, output_json=args.json)

    if args.json:
        summary = {
            "baseline": args.baseline,
            "skipped_known_failures": sorted(TIER3_KNOWN_FAILURES) if not args.include_known_failures else [],
            "total_run": len(results),
            "passed": sum(1 for r in results if r["ok"]),
            "failed": sum(1 for r in results if not r["ok"]),
            "results": results,
        }
        print(json.dumps(summary, indent=2))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
