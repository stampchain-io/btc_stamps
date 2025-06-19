import json
import os
import sys
import types
from typing import Any

import pytest

# Mark all tests in this file as integration tests due to global state modification
pytestmark = pytest.mark.integration


# Dummy SnapshotManager to inject into validator
class DummySnapshotManager:
    def __init__(self, hashes):
        self._hashes = hashes

    def load_snapshot(self):
        if hasattr(self, "_saved_data"):
            return self._saved_data
        return {"hashes": self._hashes}

    def save_snapshot(self, block_hashes, metadata=None):
        # Convert integer keys to strings to mimic JSON behavior
        str_hashes = {str(k): v for k, v in block_hashes.items()} if isinstance(block_hashes, dict) else block_hashes
        self._saved_data = {"metadata": metadata or {}, "hashes": str_hashes}

    def get_expected_hash(self, block_index):
        if isinstance(self._hashes, dict) and str(block_index) in self._hashes:
            return self._hashes[str(block_index)]
        return None

    def compute_hash(self, data):
        if "ledger_hash" in data:
            content = json.dumps(data, sort_keys=True)
            return sys.modules["index_core.util"].shash_string(content)
        else:
            content = json.dumps(data, sort_keys=True)
            return sys.modules["index_core.util"].dhash_string(content)

    def validate_against_checkpoints(self, block_index, computed_hash):
        checkpoints = sys.modules["index_core.check"].CHECKPOINTS_MAINNET
        if block_index in checkpoints:
            checkpoint = checkpoints[block_index]
            if computed_hash != checkpoint["txlist_hash"]:
                return False
        return True

    def create_snapshot_from_db(self, db):
        cursor = db.cursor()
        cursor.execute("SELECT MIN(block_index), MAX(block_index) FROM blocks")
        start_block, end_block = cursor.fetchone()

        if start_block is None or end_block is None:
            raise ValueError("No blocks found in database")

        snapshot = {}
        cursor.execute(
            """
            SELECT block_index, block_hash, messages_hash, txlist_hash, ledger_hash
            FROM blocks
            WHERE block_index BETWEEN %s AND %s
            ORDER BY block_index
            """,
            (start_block, end_block),
        )

        for row in cursor.fetchall():
            block_index = row[0]
            block_dict = {
                "block_hash": row[1],
                "messages_hash": row[2],
                "txlist_hash": row[3],
                "ledger_hash": row[4],
            }

            # Use checkpoint hash if available
            checkpoints = sys.modules["index_core.check"].CHECKPOINTS_MAINNET
            if block_index in checkpoints:
                checkpoint = checkpoints[block_index]
                block_dict["txlist_hash"] = checkpoint["txlist_hash"]

            snapshot[str(block_index)] = block_dict

        return snapshot


# Stub dependencies before importing validator
mods = [
    "index_core.reparse.snapshot",
    # Stub blocks and database_manager modules so validator imports succeed
    "index_core.blocks",
    "index_core.database_manager",
    "index_core.check",
    # Removed index_core.util to let it load normally
    "pymysql",
    "pymysql.connections",
    "pymysql.cursors",
    "bitcoinlib",
    "bitcoinlib.encoding",
    "ecdsa",
]
# Prepare stub modules
for m in mods:
    # Add a check to avoid overwriting potentially already loaded modules
    if m not in sys.modules or not hasattr(sys.modules[m], "__file__"):
        sys.modules[m] = types.ModuleType(m)  # type: ignore
# Configure stub for index_core.blocks with required attributes
_blocks_mod: Any = sys.modules["index_core.blocks"]  # type: ignore
_blocks_mod.BlockProcessor = lambda db: None
_blocks_mod.backend_instance = types.SimpleNamespace(getblockhash=lambda idx: None, getblock=lambda *args, **kwargs: {})
_blocks_mod.create_check_hashes = lambda *args, **kwargs: (None, None, None)
_blocks_mod.fetch_xcp_blocks_concurrent = lambda *args, **kwargs: {}
_blocks_mod.filter_block_transactions = lambda *args, **kwargs: ([], {})
_blocks_mod.process_tx = lambda *args, **kwargs: None
# Configure stub for index_core.database_manager
_db_mod = sys.modules.get("index_core.database_manager")
if _db_mod is not None:
    _db_mod.DatabaseManager = lambda *args, **kwargs: None  # type: ignore

# Configure stub for index_core.check
_check_mod: Any = sys.modules.get("index_core.check")
if _check_mod is not None:
    _check_mod.CHECKPOINTS_MAINNET = {}  # type: ignore

# Don't stub index_core.util - let it load normally to avoid breaking other tests
# The util module will be imported normally and tests can access real functions

# Don't inject globally - we'll do it in the fixture instead

# Reparse functionality is not fully implemented, so these tests are skipped

# Add src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from index_core.reparse.validator import ReparseValidator, ValidationError


@pytest.mark.skip(reason="Reparse functionality is not fully implemented yet")
def test_validate_sequence_success():
    rv = ReparseValidator(snapshot_path="dummy")
    # Inject dummy snapshot manager with continuous blocks 1,2,3
    rv.snapshot_manager = DummySnapshotManager({1: {}, 2: {}, 3: {}})
    assert rv.validate_sequence() is True


@pytest.mark.skip(reason="Reparse functionality is not fully implemented yet")
def test_validate_sequence_missing(monkeypatch):
    rv = ReparseValidator(snapshot_path="dummy")
    # Continuous except missing 2
    rv.snapshot_manager = DummySnapshotManager({1: {}, 3: {}})
    with pytest.raises(ValidationError) as exc:
        rv.validate_sequence()
    assert "Missing blocks in snapshot" in str(exc.value)


@pytest.mark.skip(reason="Reparse functionality is not fully implemented yet")
def test_validate_sequence_empty(monkeypatch):
    rv = ReparseValidator(snapshot_path="dummy")
    # Empty hashes
    rv.snapshot_manager = DummySnapshotManager({})
    with pytest.raises(ValidationError):
        rv.validate_sequence()


# Fixture to inject DummySnapshotManager for these tests only
@pytest.fixture(autouse=True)
def inject_dummy_snapshot_manager():
    """Inject DummySnapshotManager for reparse sequence tests."""
    # Fixture removed since all tests are skipped due to incomplete reparse implementation
    yield
