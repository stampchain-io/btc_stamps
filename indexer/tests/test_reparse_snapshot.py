import json
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest

### Stub external dependencies before importing project modules
### Use Any typing to suppress mypy attr-defined errors
# Stub boto3 to satisfy config imports
_boto3_mod: Any = types.ModuleType("boto3")
_boto3_mod.client = lambda *args, **kwargs: None
sys.modules["boto3"] = _boto3_mod
_pymysql_mod: Any = types.ModuleType("pymysql")
_pymysql_mod.connect = lambda *args, **kwargs: None
_pymysql_mod.__path__ = []
sys.modules["pymysql"] = _pymysql_mod
_conn_mod: Any = types.ModuleType("pymysql.connections")
_conn_mod.Connection = object
sys.modules["pymysql.connections"] = _conn_mod
_cur_mod: Any = types.ModuleType("pymysql.cursors")
_cur_mod.Cursor = object
_cur_mod.DictCursor = object
sys.modules["pymysql.cursors"] = _cur_mod
_btc_mod: Any = types.ModuleType("bitcoin")
sys.modules["bitcoin"] = _btc_mod
_btc_wallet: Any = types.ModuleType("bitcoin.wallet")
_btc_wallet.CBitcoinAddress = lambda addr: addr
sys.modules["bitcoin.wallet"] = _btc_wallet
_blib_mod: Any = types.ModuleType("bitcoinlib")
sys.modules["bitcoinlib"] = _blib_mod
_blib_encoding: Any = types.ModuleType("bitcoinlib.encoding")
_blib_encoding.addr_bech32_to_pubkeyhash = lambda addr: None
_blib_encoding.addr_base58_to_pubkeyhash = lambda addr: None
sys.modules["bitcoinlib.encoding"] = _blib_encoding
_ecdsa_mod: Any = types.ModuleType("ecdsa")
_ecdsa_mod.SECP256k1 = object


class _VerifyingKey:
    pass


_ecdsa_mod.VerifyingKey = _VerifyingKey
sys.modules["ecdsa"] = _ecdsa_mod
### Added stub for psutil to satisfy index_core.memory_manager imports
_psutil_mod: Any = types.ModuleType("psutil")
# Provide Process to avoid attribute errors
_psutil_mod.Process = lambda pid: types.SimpleNamespace(memory_info=lambda: None)
sys.modules["psutil"] = _psutil_mod

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
import index_core.reparse.snapshot as snapshot_module
from index_core.reparse.snapshot import SnapshotManager
from index_core.util import dhash_string, shash_string


def test_save_and_load_snapshot(tmp_path):
    snapshot_file = tmp_path / "snapshot.json"
    manager = SnapshotManager(str(snapshot_file))
    # Prepare sample hashes and metadata
    hashes = {1: {"block_hash": "a1", "messages_hash": "m1", "txlist_hash": "t1", "ledger_hash": "l1"}}
    metadata = {"foo": "bar"}
    # Save snapshot
    manager.save_snapshot(hashes, metadata=metadata)
    # Load snapshot back
    loaded = manager.load_snapshot()
    # Verify metadata and hashes
    assert "metadata" in loaded
    assert loaded["metadata"] == metadata
    assert "hashes" in loaded
    # JSON keys are strings
    assert loaded["hashes"] == {str(1): hashes[1]}


def test_get_expected_hash_absent(tmp_path):
    # No file exists yet
    snapshot_file = tmp_path / "no_file.json"
    manager = SnapshotManager(str(snapshot_file))
    # Expect None when no snapshot
    assert manager.get_expected_hash(123) is None


def test_compute_hash_functions():
    manager = SnapshotManager("dummy")
    # Non-ledger data uses double SHA256
    data = {"key": "value"}
    content = json.dumps(data, sort_keys=True)
    expected_double = dhash_string(content)
    assert manager.compute_hash(data) == expected_double

    # Ledger data uses single SHA256
    ledger_data = {"ledger_hash": "dummy"}
    content2 = json.dumps(ledger_data, sort_keys=True)
    expected_single = shash_string(content2)
    assert manager.compute_hash(ledger_data) == expected_single


def test_validate_against_checkpoints(monkeypatch):
    # Monkey-patch a known checkpoint
    monkeypatch.setitem(snapshot_module.check.CHECKPOINTS_MAINNET, 10, {"txlist_hash": "good"})
    manager = SnapshotManager("dummy")
    # Non-checkpoint block should pass
    assert manager.validate_against_checkpoints(5, "anyhash")
    # Matching checkpoint hash
    assert manager.validate_against_checkpoints(10, "good")
    # Mismatched checkpoint hash should fail
    assert not manager.validate_against_checkpoints(10, "bad")
