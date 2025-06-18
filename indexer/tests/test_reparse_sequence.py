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
        return {"hashes": self._hashes}


# Stub dependencies before importing validator
mods = [
    "index_core.reparse.snapshot",
    # Stub blocks and database_manager modules so validator imports succeed
    "index_core.blocks",
    "index_core.database_manager",
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
# Inject our DummySnapshotManager into the stub snapshot module
sys.modules["index_core.reparse.snapshot"].SnapshotManager = DummySnapshotManager  # type: ignore

# Add src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from index_core.reparse.validator import ReparseValidator, ValidationError


def test_validate_sequence_success():
    rv = ReparseValidator(snapshot_path="dummy")
    # Inject dummy snapshot manager with continuous blocks 1,2,3
    rv.snapshot_manager = DummySnapshotManager({1: {}, 2: {}, 3: {}})
    assert rv.validate_sequence() is True


def test_validate_sequence_missing(monkeypatch):
    rv = ReparseValidator(snapshot_path="dummy")
    # Continuous except missing 2
    rv.snapshot_manager = DummySnapshotManager({1: {}, 3: {}})
    with pytest.raises(ValidationError) as exc:
        rv.validate_sequence()
    assert "Missing blocks in snapshot" in str(exc.value)


def test_validate_sequence_empty(monkeypatch):
    rv = ReparseValidator(snapshot_path="dummy")
    # Empty hashes
    rv.snapshot_manager = DummySnapshotManager({})
    with pytest.raises(ValidationError):
        rv.validate_sequence()
