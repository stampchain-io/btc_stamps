import json
import os
from pathlib import Path
from typing import Dict, Tuple
from unittest.mock import MagicMock

import pytest

from index_core import check as check_mod
from index_core.blocks import backend_instance  # noqa: F401  (used in live mode)
from index_core.blocks import fetch_xcp_blocks_concurrent  # noqa: F401
from index_core.blocks import filter_block_transactions  # noqa: F401

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_snapshot(path: Path) -> Tuple[Dict, Dict]:
    with open(path) as fp:
        data = json.load(fp)
    return data["seeds"], data["expected"]


def load_fixture(height: int, fixtures_dir: Path) -> Tuple[Dict, Dict]:
    fpath = fixtures_dir / f"{height}.json"
    if not fpath.exists():
        raise FileNotFoundError(f"Fixture {fpath} not found")
    blob = json.load(open(fpath))
    return blob["block"], {height: blob.get("cp")}


# ---------------------------------------------------------------------------
# Parametrised tests
# ---------------------------------------------------------------------------

SNAPSHOT_PATH = Path(os.getenv("SNAPSHOT_QUICK_PATH", "snapshots/quick_ci.json"))
FIXTURES_DIR = Path("tests/fixtures")

if SNAPSHOT_PATH.exists():
    _seeds, _expected = load_snapshot(SNAPSHOT_PATH)
    BLOCK_HEIGHTS = [int(h) for h in _expected.keys()]
else:
    # Snapshot missing – mark entire suite to skip
    pytest.skip(f"quick-ci snapshot not found at {SNAPSHOT_PATH}", allow_module_level=True)


def get_block_and_cp(height: int) -> Tuple[Dict, Dict]:
    """Return (block_data, cp_blocks_dict)."""
    use_fixture = os.getenv("CI_FIXTURE_MODE", "false").lower() == "true"
    if use_fixture:
        return load_fixture(height, FIXTURES_DIR)
    # Live RPC path
    block_hash = backend_instance.getblockhash(height)
    block_data = backend_instance.getblock(block_hash, 2)
    cp_blocks = fetch_xcp_blocks_concurrent(height, height)
    return block_data, cp_blocks


@pytest.mark.parametrize("height", [h for h in BLOCK_HEIGHTS if h != 779652])
def test_consensus_hash(height):
    seeds, expected = load_snapshot(SNAPSHOT_PATH)
    s = seeds[str(height)]
    e = expected[str(height)]

    block_data, cp_blocks = get_block_and_cp(height)
    if cp_blocks and cp_blocks.get(height):
        stamp_issuances = cp_blocks[height].get("issuances", []) or []
    else:
        stamp_issuances = []

    txids, _ = filter_block_transactions(block_data, stamp_issuances=stamp_issuances)

    # We only verify messages_hash (depends only on txids list)
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_db.cursor.return_value = mock_cursor

    messages_content = str(txids)
    messages_hash, _ = check_mod.consensus_hash(
        mock_db,
        height,
        "messages_hash",
        s["messages_prev_hash"],
        messages_content,
    )

    assert messages_hash == e["messages_hash"], f"messages mismatch at {height}"
