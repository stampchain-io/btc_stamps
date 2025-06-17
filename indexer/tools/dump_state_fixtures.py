from __future__ import annotations

"""Dump per-block state (valid stamps + SRC-20) needed to compute txlist & ledger hashes off-chain.

The script re-implements only the *read-only* parts of production logic – it never touches the database.
It uses the existing BlockProcessor pipeline in *in-memory* mode to obtain exactly the two structures
`create_check_hashes` requires.

Usage examples:

    poetry run dump_state_fixtures --heights 820000,885000 --out tests/fixtures
    poetry run dump_state_fixtures --from-snapshot snapshots/quick_ci.json --out tests/fixtures

The resulting file format extends the existing fixture JSON with two new keys:

    {
      "block": { … },
      "cp":    { … },
      "valid": [ … ],
      "src20": [ … ]
    }

If a fixture already exists it will be *merged* (block / cp are kept as-is, new keys inserted/overwritten).
"""

import argparse
import json
import logging
from pathlib import Path
from typing import List

import config as _cfg  # deferred import to avoid overhead when not needed
from index_core.blocks import (
    backend_instance,
    fetch_xcp_blocks_concurrent,
)
from index_core.block_validation import filter_block_transactions
from index_core.transaction_utils import process_tx
from index_core.reparse.validator import InMemoryBlockProcessor  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("dump_state_fixtures")


def parse_heights(arg: str) -> List[int]:
    heights: List[int] = []
    for part in arg.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = map(int, part.split("-", 1))
            heights.extend(range(start, end + 1))
        else:
            heights.append(int(part))
    return sorted(set(heights))


def compute_state(height: int):
    """Return (valid_stamps, src20_list) for *height* using in-memory processing only."""
    # Fetch block data
    block_hash = backend_instance.getblockhash(height)
    block_data = backend_instance.getblock(block_hash, 2)
    if not block_data:
        raise RuntimeError(f"Empty block data for height {height}")

    # Fetch CP issuances
    cp_blocks = fetch_xcp_blocks_concurrent(height, height)
    stamp_issuances = cp_blocks.get(height, {}).get("issuances", []) if isinstance(cp_blocks, dict) else []

    # Filter BTC transactions relevant to Stamps
    txids, raw_txs = filter_block_transactions(block_data, stamp_issuances=stamp_issuances)

    # Special handling for CP genesis: keep only issuance transactions present in raw_txs
    # (see same logic in ReparseValidator.compute_block_hashes)
    if height == _cfg.CP_STAMP_GENESIS_BLOCK:
        raw_txs = {iss["tx_hash"]: raw_txs[iss["tx_hash"]] for iss in stamp_issuances if iss.get("tx_hash") in raw_txs}

    # Run BlockProcessor logic fully in-memory
    proc = InMemoryBlockProcessor()
    for tx_hash in txids:  # iterate in same order
        if tx_hash not in raw_txs:
            # Skip txids that weren't captured in raw_txs (shouldn't happen except genesis)
            continue
        result = process_tx(None, tx_hash, height, stamp_issuances, raw_txs)
        if getattr(result, "data", None) is not None:
            result = result._replace(block_index=height, block_time=block_data["time"])
            proc.process_transaction_results([result])

    return proc.valid_stamps_in_block, proc.processed_src20_in_block


def dump_fixture(height: int, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{height}.json"

    try:
        # Merge with existing file if present
        if path.exists():
            blob = json.load(open(path))
        else:
            blob = {}

        valid, src20 = compute_state(height)
        blob["valid"] = valid
        blob["src20"] = src20

        # Rewrite file with pretty formatting for diff-friendly output
        with open(path, "w") as fp:
            json.dump(blob, fp, indent=2, sort_keys=True, ensure_ascii=False)
        logger.info(f"Wrote state fixture for {height} -> {path}")
    except Exception as e:
        logger.error(f"Failed to dump state for {height}: {e}")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump valid stamp & SRC-20 state for CI fixtures")
    parser.add_argument("--heights", help="Comma-separated list or range e.g. 820000,885000 or 820000-820100")
    parser.add_argument("--from-snapshot", help="Path to quick_ci.json to derive heights from", default=None)
    parser.add_argument("--out", default="tests/fixtures", help="Output directory")
    args = parser.parse_args()

    heights: List[int] = []
    if args.heights:
        heights.extend(parse_heights(args.heights))
    if args.from_snapshot:
        snap = Path(args.from_snapshot)
        if not snap.exists():
            raise FileNotFoundError(snap)
        data = json.load(open(snap))
        heights.extend(int(h) for h in data.get("expected", {}).keys())

    if not heights:
        raise SystemExit("No heights specified. Use --heights or --from-snapshot")

    for h in sorted(set(heights)):
        dump_fixture(h, Path(args.out))


if __name__ == "__main__":
    main()
