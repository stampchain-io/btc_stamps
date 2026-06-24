#!/usr/bin/env python3
"""Tier 3 subprocess-per-block reparse runner (issue #770 Option B).

For each block in the curated set (``indexer/snapshots/ci_consensus_hashes.json``)
spawn a fresh ``python -m indexer.ci.smoke_parser_validation --block N`` subprocess
and aggregate pass/fail. The subprocess boundary gives us automatic state
isolation between blocks — module globals, ``cache_manager["stamp"]["counter"]``,
``util.CURRENT_BLOCK_INDEX``, etc. are reborn per block, so we sidestep the
in-process state-carry problem documented in #775.

Why this exists alongside ``ci_reparse_multi.py`` (Tier 1):
- Tier 1 runs all blocks in a single process with manual cache seeding. Fast
  (~5 min for 38) but fundamentally limited by ``InMemoryBlockProcessor``'s
  structural divergence from the production ``StampProcessor`` (#775).
- Tier 3 (this file) trades some wall-clock for state-isolation correctness.
  Each subprocess loads the Rust parser + reads the snapshot afresh; expect
  ~10 min for 38 blocks. Acceptable for per-PR CI signal.

Both can coexist in CI for a bake cycle — Tier 1 catches the fast smoke
issues, Tier 3 catches the cross-block state-pollution issues that Tier 1
silently masks.

Usage::

    python3 indexer/ci/ci_reparse_subprocess.py \\
        --baseline indexer/snapshots/ci_consensus_hashes.json

    # Run a subset (useful when iterating locally)
    python3 indexer/ci/ci_reparse_subprocess.py --limit 5

    # JSON output for downstream tooling
    python3 indexer/ci/ci_reparse_subprocess.py --json > results.json

Exit codes: 0 = all blocks pass, 1 = any block fails, 2 = config/setup error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BASELINE = os.path.normpath(os.path.join(HERE, "..", "snapshots", "ci_consensus_hashes.json"))

# Default per-block subprocess timeout. Rust parser init + Bitcoin fetch +
# CP fetch for a stamp-heavy block ~30-45s on a warm cache; 120s is a
# generous ceiling that still catches truly stuck runs.
DEFAULT_PER_BLOCK_TIMEOUT = 120


def _load_baseline(path: str) -> List[int]:
    """Return the sorted list of block_index values from the curated baseline."""
    with open(path) as fh:
        data = json.load(fh)
    hashes = data.get("hashes")
    if not isinstance(hashes, dict):
        raise SystemExit(f"baseline {path}: 'hashes' is missing or not a dict")
    return sorted(int(k) for k in hashes.keys())


def _run_one(block_index: int, timeout_sec: int) -> Tuple[bool, float, str]:
    """Spawn a single ``smoke_parser_validation --block N`` subprocess.

    Returns ``(ok, duration_sec, stderr_tail)``. ``stderr_tail`` is the last
    ~2KB of stderr — enough to surface the failure reason in CI logs without
    overwhelming them.
    """
    # Invoke as a script rather than `-m indexer.ci.smoke_parser_validation`:
    # the indexer/ tree isn't installed as a Python package, and the smoke
    # driver does its own ``sys.path`` munging when run as a script.
    smoke_path = os.path.join(HERE, "smoke_parser_validation.py")
    cmd = [sys.executable, smoke_path, "--block", str(block_index)]
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired as e:
        return (False, time.monotonic() - start, f"TIMEOUT after {timeout_sec}s: {e}")
    duration = time.monotonic() - start
    ok = proc.returncode == 0
    # Always preserve the tail of stderr; on failure also keep the tail of
    # stdout so we surface what the validator printed before exiting non-zero.
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
    """Run the subprocess runner over ``blocks`` and return ``(exit_code, results)``.

    ``results`` is a list of ``{block, ok, duration_sec, stderr_tail}`` dicts.
    Exit code: 0 if all pass, 1 if any fail (or fail_fast tripped early).
    """
    results: List[Dict] = []
    fail_count = 0
    overall_start = time.monotonic()

    for i, block in enumerate(blocks, 1):
        if not output_json:
            print(f"[{i}/{len(blocks)}] block {block}: running...", flush=True)
        ok, duration, stderr_tail = _run_one(block, timeout_sec)
        result = {"block": block, "ok": ok, "duration_sec": round(duration, 2)}
        if not ok:
            result["stderr_tail"] = stderr_tail
            fail_count += 1
        results.append(result)
        if not output_json:
            status = "✓" if ok else "✗"
            print(f"[{i}/{len(blocks)}] block {block}: {status} ({duration:.1f}s)", flush=True)
            if not ok:
                # Print the tail immediately so a CI operator can see the
                # failure reason in line, not just in the JSON summary.
                print(stderr_tail, flush=True)
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
    ap.add_argument("--limit", type=int, default=0, help="if >0, only run the first N blocks (for local iteration)")
    ap.add_argument("--fail-fast", action="store_true", help="stop on first failing block")
    ap.add_argument("--json", action="store_true", help="emit a single JSON summary on stdout instead of per-block lines")
    args = ap.parse_args()

    try:
        blocks = _load_baseline(args.baseline)
    except (FileNotFoundError, json.JSONDecodeError, SystemExit) as e:
        print(f"ERROR loading baseline: {e}", file=sys.stderr)
        return 2

    if args.limit and args.limit > 0:
        blocks = blocks[: args.limit]

    if not blocks:
        print(f"ERROR: no blocks in baseline {args.baseline}", file=sys.stderr)
        return 2

    exit_code, results = run(blocks, args.timeout, fail_fast=args.fail_fast, output_json=args.json)

    if args.json:
        summary = {
            "baseline": args.baseline,
            "total": len(results),
            "passed": sum(1 for r in results if r["ok"]),
            "failed": sum(1 for r in results if not r["ok"]),
            "results": results,
        }
        print(json.dumps(summary, indent=2))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
