#!/usr/bin/env python3
"""Deterministic stratified-random block selection for the Tier-3 consensus set.

Issue #778 (item 1): grow the curated Tier-3 consensus-CI baseline
(``indexer/snapshots/ci_consensus_hashes.json`` / the ``CI_BLOCKS`` array in
``refresh-consensus-hashes.sh``) beyond the hand-picked consensus-boundary
triples, by adding a reproducible, auditable, stratified-random sample of
blocks that the DB-free Tier-3 runner can fully reproduce.

## The selection criterion (two parts)

1. **Offline pre-filter (necessary condition).** A block ``N`` is a *candidate*
   iff, in ``reference_hashes.json``:
     * ``ledger_hash[N] == ledger_hash[N-1]`` — no net SRC-20 ledger mutation,
       so the DB-free runner (seeded with the prev ledger hash) can reproduce
       ``ledger_hash`` without prior balances/mints/deploys; AND
     * ``txlist_hash[N] != txlist_hash[N-1]`` — real stamp / Counterparty parse
       activity this block, so the block gives *meaningful* Tier-3 coverage; AND
     * ``N`` is not already in ``CI_BLOCKS`` and is not a runtime checkpoint
       (``CHECKPOINTS_MAINNET``). Checkpoint blocks are skipped because the
       validator short-circuits them (``is a checkpoint; skipping``), so they
       contribute no real reparse coverage; AND
     * ``int(sha256(str(N)).hexdigest(), 16) % K == 0`` — a stable pseudo-random
       1/K subsample so the choice is spread, deterministic and regenerable by
       anyone (``K`` = ``SAMPLE_MODULUS`` below).

   All four are computable purely from committed files — no network needed.

2. **Empirical Tier-3 gate (binding, with ``--validate``).** The offline
   pre-filter is a strong *necessary* condition but is empirically **not
   sufficient**: a handful of early native-BTC-SRC20 blocks (e.g. 793074, right
   at ``BTC_SRC20_GENESIS_BLOCK``) are ledger-unchanged yet still fail to
   reproduce ``txlist_hash`` in the DB-free runner. So the *binding* criterion
   is that the block actually passes ``ci/smoke_parser_validation.py --block N``
   end-to-end (block + txlist + ledger). With ``--validate`` this script runs
   that gate per candidate and keeps only full-pass blocks — guaranteeing every
   selected block is Tier-3-green and NONE need to land in
   ``TIER3_CROSS_BLOCK_LEDGER``. This is strictly stronger than the offline
   classifier alone, never weaker.

## Stratification

``TARGET_PER_EPOCH`` blocks are chosen from each protocol epoch (boundaries
from ``indexer/src/config.py``). Within an epoch the candidates are taken
**evenly spaced** across the deterministic candidate stream (not clustered at
the epoch start, where the heuristic is weakest), and on a validation failure
the next un-used candidate after that position is tried — keeping the result
deterministic and reproducible.

## Usage

    # Offline: print the deterministic candidate stream + the spread picks.
    poetry run python ci/select_random_ci_blocks.py

    # Binding selection: validate each pick via the Tier-3 runner, replacing
    # any failures deterministically; emit the CI_BLOCKS snippet to paste into
    # refresh-consensus-hashes.sh.
    poetry run python ci/select_random_ci_blocks.py --validate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
REFERENCE = os.path.join(REPO, "indexer", "snapshots", "reference_hashes.json")
REFRESH_SH = os.path.join(HERE, "refresh-consensus-hashes.sh")
CHECK_PY = os.path.join(REPO, "indexer", "src", "index_core", "check.py")
SMOKE = os.path.join(HERE, "smoke_parser_validation.py")

# Stable pseudo-random subsample rate: keep blocks where
# int(sha256(str(N)).hexdigest(), 16) % SAMPLE_MODULUS == 0. Chosen so every
# epoch (including the small ~5k-block OLGA and CP-SRC20 eras) yields well more
# candidates than TARGET_PER_EPOCH, leaving headroom for the validation gate.
SAMPLE_MODULUS = 23
TARGET_PER_EPOCH = 8

# Stay clear of consensus-activation boundaries: the in-memory reparse path is
# known to structurally diverge on `txlist_hash` at/adjacent to activation
# blocks (e.g. 793074 near BTC_SRC20_GENESIS; the STOP_BASE64_REPAIR boundary
# 784550 — see #775) even when `ledger_hash` is unchanged. Those boundary
# triples are already covered explicitly in CI_BLOCKS, so we exclude a margin
# around every known activation height and keep the random sample in the
# interior of each epoch.
BOUNDARY_MARGIN = 50
ACTIVATION_HEIGHTS = [
    779652,  # CP_STAMP_GENESIS_BLOCK
    784550,  # STOP_BASE64_REPAIR
    788041,  # CP_SRC20_GENESIS_BLOCK
    792370,  # CP_SRC721_GENESIS_BLOCK
    793068,  # BTC_SRC20_GENESIS_BLOCK
    796000,  # CP_SRC20_END_BLOCK
    815130,  # CP_BMN_FEAT_BLOCK_START
    833000,  # CP_P2WSH_FEAT_BLOCK_START
    865000,  # BTC_SRC20_OLGA_BLOCK
    866000,  # CP_SUBASSET_FEAT_BLOCK_START
    870652,  # BTC_SRC101_GENESIS_BLOCK
    872200,  # BTC_SRC101_IMG_OPTIONAL_BLOCK
    940000,  # BTC_SRC101_OLGA_BLOCK (planned)
]

# Protocol epochs, boundaries verified against indexer/src/config.py:
#   CP_STAMP_GENESIS_BLOCK   = 779652
#   CP_SRC20_GENESIS_BLOCK   = 788041
#   BTC_SRC20_GENESIS_BLOCK  = 793068
#   BTC_SRC20_OLGA_BLOCK     = 865000
#   BTC_SRC101_GENESIS_BLOCK = 870652
# Upper bound 955061 = max block in reference_hashes.json.
EPOCHS: List[Tuple[int, int, str]] = [
    (779652, 788040, "epoch1 (pre-SRC20 / CP_STAMP era)"),
    (788041, 793067, "epoch2 (CP-SRC20 era)"),
    (793068, 864999, "epoch3 (BTC-SRC20 pre-OLGA)"),
    (865000, 870651, "epoch4 (OLGA era)"),
    (870652, 955061, "epoch5 (SRC-101 / post-OLGA)"),
]


def load_reference() -> Dict[str, dict]:
    with open(REFERENCE) as fh:
        return json.load(fh)["hashes"]


def load_checkpoints() -> set:
    txt = open(CHECK_PY).read()
    m = re.search(r"CHECKPOINTS_MAINNET.*?\{(.*?)\n\}", txt, re.S)
    if not m:
        return set()
    return {int(k) for k in re.findall(r"(\d+):\s*\{", m.group(1))}


def load_existing_ci_blocks() -> set:
    txt = open(REFRESH_SH).read()
    m = re.search(r"CI_BLOCKS=\((.*?)\n\)", txt, re.S)
    body = m.group(1) if m else ""
    return {int(x) for x in re.findall(r'"(\d+):', body)}


def candidate_stream(ref: Dict[str, dict], lo: int, hi: int, skip: set) -> List[int]:
    """Deterministic ascending stream of offline candidates for [lo, hi]."""
    out: List[int] = []
    for n in range(lo + 1, hi + 1):
        if n in skip:
            continue
        if any(abs(n - h) <= BOUNDARY_MARGIN for h in ACTIVATION_HEIGHTS):
            continue
        cur, prev = ref.get(str(n)), ref.get(str(n - 1))
        if cur is None or prev is None:
            continue
        if cur["ledger_hash"] != prev["ledger_hash"]:
            continue  # ledger mutated -> needs cross-block state -> not Tier-3
        if cur["txlist_hash"] == prev["txlist_hash"]:
            continue  # no parse activity -> not meaningful coverage
        if int(hashlib.sha256(str(n).encode()).hexdigest(), 16) % SAMPLE_MODULUS != 0:
            continue
        out.append(n)
    return out


def evenly_spaced_indices(length: int, count: int) -> List[int]:
    if length <= 0:
        return []
    if count >= length:
        return list(range(length))
    return [round(i * (length - 1) / (count - 1)) for i in range(count)] if count > 1 else [0]


def validate_block(n: int, retries: int = 6) -> str:
    """Run the Tier-3 runner. Returns one of:
    'pass'  — block fully reproduces (block + txlist + ledger)
    'fail'  — clean, deterministic Tier-3 failure (hash mismatch / parse error)
    'infra' — could not be validated (rate-limit / network exhaustion) after
              retries; the block is NOT classified, must not be silently kept.
    """
    for attempt in range(retries):
        proc = subprocess.run(
            [sys.executable, SMOKE, "--block", str(n)],
            capture_output=True,
            text=True,
            cwd=os.path.join(REPO, "indexer"),
        )
        out = proc.stdout + proc.stderr
        if proc.returncode == 0 and f"validate_block({n}) = True" in out:
            return "pass"
        # A real Tier-3 divergence reported by the validator.
        if (
            f"validate_block({n}) = False" in out
            or "Hash mismatch for block" in out
            or "'bytes' object has no attribute" in out
        ):
            return "fail"
        # Otherwise treat as infra (rate-limit exhaustion / transient network).
        wait = 20 * (attempt + 1)
        print(f"    block {n}: infra/rate-limit (attempt {attempt + 1}); backing off {wait}s", file=sys.stderr)
        time.sleep(wait)
    return "infra"


def select_epoch(stream: List[int], validate: bool, pace: float) -> List[int]:
    if not validate:
        idxs = evenly_spaced_indices(len(stream), TARGET_PER_EPOCH)
        return [stream[i] for i in idxs]
    # Validate evenly-spaced picks; on failure advance to the next unused
    # candidate after that position (deterministic) until a full pass.
    chosen: List[int] = []
    used: set = set()
    start_idxs = evenly_spaced_indices(len(stream), TARGET_PER_EPOCH)
    for start in start_idxs:
        i = start
        while i < len(stream):
            if i in used:
                i += 1
                continue
            used.add(i)
            n = stream[i]
            print(f"    validating {n} ...", file=sys.stderr)
            verdict = validate_block(n)
            if verdict == "pass":
                chosen.append(n)
                break
            if verdict == "fail":
                print(f"    {n} failed Tier-3 (clean divergence); advancing", file=sys.stderr)
            else:  # infra — could not validate; skip but make it loud
                print(f"    {n} UNVALIDATED (infra/rate-limit); skipping, NOT keeping", file=sys.stderr)
            i += 1
            time.sleep(pace)
        time.sleep(pace)
    return sorted(chosen)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true", help="run the Tier-3 runner per candidate; keep only full-pass blocks")
    ap.add_argument("--pace", type=float, default=2.0, help="seconds to sleep between validations")
    args = ap.parse_args()

    ref = load_reference()
    skip = load_existing_ci_blocks() | load_checkpoints()

    all_chosen: List[Tuple[int, str]] = []
    for lo, hi, label in EPOCHS:
        stream = candidate_stream(ref, lo, hi, skip)
        print(
            f"# {label}: {len(stream)} offline candidates " f"(K={SAMPLE_MODULUS}, ledger-unchanged + txactivity)",
            file=sys.stderr,
        )
        picks = select_epoch(stream, args.validate, args.pace)
        for n in picks:
            all_chosen.append((n, label))

    print("\n# --- CI_BLOCKS snippet (paste into refresh-consensus-hashes.sh) ---")
    for n, label in all_chosen:
        print(f'  "{n}:random-sample {label}"')
    print(f"\n# total new blocks: {len(all_chosen)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
