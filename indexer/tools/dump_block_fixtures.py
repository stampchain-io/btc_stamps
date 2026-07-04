import argparse
import json
import logging
from pathlib import Path
from typing import List

from index_core.blocks import backend_instance, fetch_xcp_blocks_concurrent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("dump_block_fixtures")


def dump_fixture(height: int, out_dir: Path) -> None:
    """Fetch Bitcoin block + Counterparty issuance JSON and write to file."""
    try:
        block_hash = backend_instance.getblockhash(height)
        block_data = backend_instance.getblock(block_hash, 2)
        if not block_data:
            raise RuntimeError(f"Empty block data for height {height}")

        # Counterparty block data (issuances)
        cp_blocks = fetch_xcp_blocks_concurrent(height, height)
        cp_data = cp_blocks.get(height) if isinstance(cp_blocks, dict) else None

        fixture = {"block": block_data, "cp": cp_data}
        out_path = out_dir / f"{height}.json"
        with open(out_path, "w") as fp:
            json.dump(fixture, fp)
        logger.info(f"Wrote fixture for {height} to {out_path}")
    except Exception as e:
        logger.error(f"Failed to dump fixture for {height}: {e}")
        raise


def parse_heights(arg: str) -> List[int]:
    """Parse comma-separated list or single int."""
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump Bitcoin + CP block fixtures for CI")
    parser.add_argument("--heights", help="Comma-separated list or range e.g. 779652,820000 or 779652-779660")
    parser.add_argument("--from-snapshot", help="Path to quick_ci.json to derive heights from", default=None)
    parser.add_argument("--out", default="tests/fixtures", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    heights = []
    if args.heights:
        heights.extend(parse_heights(args.heights))
    if args.from_snapshot:
        import json

        snap_path = Path(args.from_snapshot)
        if not snap_path.exists():
            raise FileNotFoundError(f"Snapshot {snap_path} not found")
        data = json.load(open(snap_path))
        heights.extend(int(h) for h in data.get("expected", {}).keys())

    if not heights:
        raise SystemExit("No heights specified. Use --heights or --from-snapshot")

    heights = sorted(set(heights))
    logger.info(f"Dumping fixtures for {len(heights)} heights -> {out_dir}")
    for h in heights:
        dump_fixture(h, out_dir)


if __name__ == "__main__":
    main()
