import os
import sys
import types
from typing import Any

import pytest

# Mark all tests in this file as integration tests due to global module stubbing
pytestmark = pytest.mark.integration

# Stub external dependencies before importing project modules
# Stub boto3
_boto3_mod: Any = types.ModuleType("boto3")
_boto3_mod.client = lambda *args, **kwargs: None
sys.modules["boto3"] = _boto3_mod
# Stub pymysql for database_manager import
_pymysql_mod: Any = types.ModuleType("pymysql")
_pymysql_mod.connect = lambda *args, **kwargs: None
_pymysql_mod.__path__ = []
sys.modules["pymysql"] = _pymysql_mod
# Shim pymysql.connections with Connection symbol
_pconn_mod: Any = types.ModuleType("pymysql.connections")
_pconn_mod.Connection = type("Connection", (), {})
sys.modules["pymysql.connections"] = _pconn_mod
# Shim pymysql.cursors with Cursor and DictCursor symbols
_pcurs_mod: Any = types.ModuleType("pymysql.cursors")
_pcurs_mod.Cursor = type("Cursor", (), {})
_pcurs_mod.DictCursor = type("DictCursor", (), {})
sys.modules["pymysql.cursors"] = _pcurs_mod
# Stub bitcoin modules for util import - REMOVING CONFLICTING STUBS
# _btc_mod: Any = types.ModuleType("bitcoin")
# sys.modules["bitcoin"] = _btc_mod
# _btc_wallet: Any = types.ModuleType("bitcoin.wallet")
# _btc_wallet.CBitcoinAddress = lambda addr: addr
# sys.modules["bitcoin.wallet"] = _btc_wallet
_blib_mod: Any = types.ModuleType("bitcoinlib")
sys.modules["bitcoinlib"] = _blib_mod
_blib_encoding: Any = types.ModuleType("bitcoinlib.encoding")
_blib_encoding.addr_bech32_to_pubkeyhash = lambda addr: None
_blib_encoding.addr_base58_to_pubkeyhash = lambda addr: None
sys.modules["bitcoinlib.encoding"] = _blib_encoding
_ecdsa_mod: Any = types.ModuleType("ecdsa")
_ecdsa_mod.SECP256k1 = object
_ecdsa_mod.VerifyingKey = type("VK", (), {})
sys.modules["ecdsa"] = _ecdsa_mod

# Remove conflicting psutil stub
# _psutil_mod: Any = types.ModuleType("psutil")
# _psutil_mod.Process = lambda pid: types.SimpleNamespace(memory_info=lambda: None)
# sys.modules["psutil"] = _psutil_mod

# Add src directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import config
import index_core.reparse.snapshot as snapshot_module
from index_core.reparse.snapshot import SnapshotManager


class FakeCursor:
    def __init__(self, minmax, rows):
        self._minmax = minmax
        self._rows = rows
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchone(self):
        return self._minmax

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


class FakeDB:
    def __init__(self, minblock, maxblock, rows):
        self.cursor_obj = FakeCursor((minblock, maxblock), rows)

    def cursor(self):
        return self.cursor_obj


def test_create_snapshot_from_db_with_checkpoints(monkeypatch):
    # Arrange
    monkeypatch.setattr(config, "CP_STAMP_GENESIS_BLOCK", 1)
    # Monkey-patch checkpoints
    monkeypatch.setitem(snapshot_module.check.CHECKPOINTS_MAINNET, 2, {"txlist_hash": "cp2"})
    # Prepare fake DB with blocks 1..3
    rows = [
        (1, "bh1", "mh1", "tl1", "lh1"),
        (2, "bh2", "mh2", "tl2", "lh2"),
        (3, "bh3", "mh3", "tl3", "lh3"),
    ]
    fake_db = FakeDB(1, 3, rows)
    mgr = snapshot_module.SnapshotManager("dummy")

    # Act
    snapshot = mgr.create_snapshot_from_db(fake_db)

    # Assert
    assert set(snapshot.keys()) == {"1", "2", "3"}
    assert snapshot["1"]["txlist_hash"] == "tl1"
    assert snapshot["2"]["txlist_hash"] == "cp2"
    assert snapshot["3"]["txlist_hash"] == "tl3"


def test_create_snapshot_from_db_empty(monkeypatch):
    monkeypatch.setattr(config, "CP_STAMP_GENESIS_BLOCK", 10)
    fake_db = FakeDB(None, None, [])
    mgr = snapshot_module.SnapshotManager("dummy")
    with pytest.raises(ValueError):
        mgr.create_snapshot_from_db(fake_db)
