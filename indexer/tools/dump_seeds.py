import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List

from index_core.database_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("dump_seeds")


def fetch_hashes(db, height: int) -> Dict[str, str]:
    """Return consensus hashes for given height."""
    with db.cursor() as cursor:
        cursor.execute(
            """SELECT messages_hash, txlist_hash, ledger_hash FROM blocks WHERE block_index = %s""",
            (height,),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"No block {height} in database")
        return {"messages_hash": row[0], "txlist_hash": row[1], "ledger_hash": row[2]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump seed + expected hashes for quick CI snapshot")
    parser.add_argument(
        "--heights",
        required=True,
        help="Comma-separated list of block heights, e.g. 779700,820000,885000",
    )
    parser.add_argument("--out", default="snapshots/quick_ci.json", help="Output snapshot path")
    parser.add_argument("--include-checkpoints", action="store_true", help="Include all CHECKPOINTS_MAINNET heights")
    args = parser.parse_args()

    heights: List[int] = []
    if args.heights.strip():
        heights.extend(int(h.strip()) for h in args.heights.split(",") if h.strip())

    if args.include_checkpoints:
        from index_core import check as check_mod

        heights.extend(check_mod.CHECKPOINTS_MAINNET.keys())

    heights = sorted(set(heights))

    dbm = DatabaseManager()
    db = dbm.connect()
    try:
        seeds: Dict[str, Dict[str, str]] = {}
        expected: Dict[str, Dict[str, str]] = {}
        for h in heights:
            logger.info(f"Fetching hashes for {h} and {h-1}")
            try:
                prev_hashes = fetch_hashes(db, h - 1)
            except ValueError:
                prev_hashes = {
                    "messages_hash": "0" * 64,
                    "txlist_hash": "0" * 64,
                    "ledger_hash": "0" * 64,
                }
            cur_hashes = fetch_hashes(db, h)
            seeds[str(h)] = {
                "messages_prev_hash": prev_hashes["messages_hash"],
                "txlist_prev_hash": prev_hashes["txlist_hash"],
                "ledger_prev_hash": prev_hashes["ledger_hash"],
            }
            expected[str(h)] = cur_hashes

        snapshot = {"seeds": seeds, "expected": expected}
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as fp:
            json.dump(snapshot, fp, indent=2)
        logger.info(f"Wrote snapshot to {out_path}")
    finally:
        db.close()


if __name__ == "__main__":
    main() 