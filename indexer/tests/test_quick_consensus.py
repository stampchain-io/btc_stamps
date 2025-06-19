import json
import os
from pathlib import Path
from typing import Dict, Tuple
from unittest.mock import MagicMock

import pytest

from index_core import check as check_mod
from index_core.block_validation import create_check_hashes  # noqa: F401
from index_core.block_validation import filter_block_transactions  # noqa: F401
from index_core.blocks import backend_instance  # noqa: F401  (used in live mode)
from index_core.blocks import fetch_xcp_blocks_concurrent  # noqa: F401

# ---------------------------------------------------------------------------
# Test Environment Isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_rpc_environment_variables():
    """Clear RPC-related environment variables that could interfere with tests."""
    rpc_env_vars = [
        "RPC_IP",
        "RPC_PORT",
        "RPC_USER",
        "RPC_PASSWORD",
        "RPC_SSL",
        "CP_RPC_IP",
        "CP_RPC_PORT",
        "CP_RPC_USER",
        "CP_RPC_PASSWORD",
        "CP_FALLBACK_MODE",
    ]

    original_values = {}
    for var in rpc_env_vars:
        original_values[var] = os.environ.get(var)
        if var in os.environ:
            del os.environ[var]

    yield

    # Restore original values
    for var, value in original_values.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_snapshot(path: Path) -> Tuple[Dict, Dict]:
    with open(path) as fp:
        data = json.load(fp)
    return data["seeds"], data["expected"]


def load_fixture(height: int, fixtures_dir: Path) -> Tuple[Dict, Dict, list, list]:
    """Return (block_data, cp_blocks_dict, valid_stamps, src20_state)."""
    fpath = fixtures_dir / f"{height}.json"
    if not fpath.exists():
        raise FileNotFoundError(f"Fixture {fpath} not found")
    blob = json.load(open(fpath))
    block_data = blob["block"]
    cp_dict = {height: blob.get("cp")}
    valid = blob.get("valid", [])
    src20 = blob.get("src20", [])
    return block_data, cp_dict, valid, src20


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


def get_block_and_cp(height: int):
    """Return (block_data, cp_blocks_dict, valid_stamps, src20_state)."""
    # Check multiple conditions to determine if we should use fixtures:
    # 1. CI_FIXTURE_MODE explicitly set to "true"
    # 2. TESTING environment variable is set (general test mode)
    # 3. No explicit LIVE_MODE environment variable set
    use_fixture = (
        os.getenv("CI_FIXTURE_MODE", "false").lower() == "true"
        or os.getenv("TESTING", "false").lower() in ("1", "true")
        or os.getenv("LIVE_MODE", "false").lower() != "true"
    )

    if use_fixture:
        return load_fixture(height, FIXTURES_DIR)

    # Live RPC path – we do *not* compute valid/src20 lists here (would require full parsing).
    block_hash = backend_instance.getblockhash(height)
    block_data = backend_instance.getblock(block_hash, 2)
    cp_blocks = fetch_xcp_blocks_concurrent(height, height)
    return block_data, cp_blocks, [], []


@pytest.mark.parametrize("height", [h for h in BLOCK_HEIGHTS if h != 779652])
def test_consensus_hash(height):
    seeds, expected = load_snapshot(SNAPSHOT_PATH)
    s = seeds[str(height)]
    e = expected[str(height)]

    block_data, cp_blocks, valid, src20 = get_block_and_cp(height)

    if cp_blocks and cp_blocks.get(height):
        stamp_issuances = cp_blocks[height].get("issuances", []) or []
    else:
        stamp_issuances = []

    txids, _ = filter_block_transactions(block_data, stamp_issuances=stamp_issuances)

    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_db.cursor.return_value = mock_cursor

    # Decide which hashes to validate based on availability of valid/src20 lists
    has_state = bool(valid) or bool(src20)

    if has_state:
        # Full validation using create_check_hashes (fast, off-chain)
        new_ledger, new_txlist, new_messages = create_check_hashes(
            mock_db,
            height,
            valid,
            src20,
            txids,
            s["ledger_prev_hash"],
            s["txlist_prev_hash"],
            s["messages_prev_hash"],
        )

        assert new_messages == e["messages_hash"], f"messages mismatch at {height}"
        assert new_txlist == e["txlist_hash"], f"txlist mismatch at {height}"
        if e["ledger_hash"]:
            assert new_ledger == e["ledger_hash"], f"ledger mismatch at {height}"
    else:
        # Fallback: validate only messages_hash as before
        messages_content = str(txids)
        messages_hash, _ = check_mod.consensus_hash(
            mock_db,
            height,
            "messages_hash",
            s["messages_prev_hash"],
            messages_content,
        )
        assert messages_hash == e["messages_hash"], f"messages mismatch at {height} (messages-only mode)"
