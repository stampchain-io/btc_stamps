import os
import sys
import types

# from pathlib import Path # Unused
from typing import Any

import pytest

from tests.test_isolation_utils import IsolationManager

# Store original state for cleanup
_modules_to_mock = [
    "boto3",
    "pymysql",
    "pymysql.connections",
    "pymysql.cursors",
    "bitcoinlib",
    "bitcoinlib.encoding",
    "ecdsa",
    "index_core.blocks",
]


@pytest.fixture(autouse=True, scope="module")
def module_isolation():
    """Provide comprehensive isolation for this module."""
    with IsolationManager().isolate_sys_modules(_modules_to_mock).isolate_sys_path():
        # Stub external dependencies before importing project modules
        # Use Any typing to suppress mypy attr-defined errors

        # Stub boto3 for config imports
        _boto3_mod: Any = types.ModuleType("boto3")
        _boto3_mod.client = lambda *_args, **_kwargs: None
        sys.modules["boto3"] = _boto3_mod
        _pymysql_mod: Any = types.ModuleType("pymysql")
        _pymysql_mod.connect = lambda *_args, **_kwargs: None
        _pymysql_mod.__path__ = []
        sys.modules["pymysql"] = _pymysql_mod
        _conn_mod: Any = types.ModuleType("pymysql.connections")
        _conn_mod.Connection = object
        sys.modules["pymysql.connections"] = _conn_mod
        _cur_mod: Any = types.ModuleType("pymysql.cursors")
        _cur_mod.Cursor = object
        _cur_mod.DictCursor = object
        sys.modules["pymysql.cursors"] = _cur_mod

        # Stub bitcoinlib module for index_core.util imports
        _blib_mod: Any = types.ModuleType("bitcoinlib")
        sys.modules["bitcoinlib"] = _blib_mod
        _blib_encoding: Any = types.ModuleType("bitcoinlib.encoding")
        _blib_encoding.addr_bech32_to_pubkeyhash = lambda _addr: None
        _blib_encoding.addr_base58_to_pubkeyhash = lambda _addr: None
        sys.modules["bitcoinlib.encoding"] = _blib_encoding

        # Stub ecdsa module for index_core.util imports
        _ecdsa_mod: Any = types.ModuleType("ecdsa")
        _ecdsa_mod.SECP256k1 = object

        class _VerifyingKey:
            pass

        _ecdsa_mod.VerifyingKey = _VerifyingKey
        sys.modules["ecdsa"] = _ecdsa_mod

        _blocks_mod: Any = types.ModuleType("index_core.blocks")
        _blocks_mod.BlockProcessor = lambda _db: None
        _blocks_mod.backend_instance = types.SimpleNamespace(
            getblockhash=lambda _idx: None, getblock=lambda *_args, **_kwargs: {}
        )
        _blocks_mod.create_check_hashes = lambda *_args, **_kwargs: (None, None, None)
        _blocks_mod.fetch_xcp_blocks_concurrent = lambda *_args, **_kwargs: {}
        _blocks_mod.filter_block_transactions = lambda *_args, **_kwargs: ([], {})
        _blocks_mod.process_tx = lambda *_args, **_kwargs: types.SimpleNamespace(
            data=None, tx_hash=None, _replace=lambda **_kw: None
        )
        sys.modules["index_core.blocks"] = _blocks_mod

        # Add the src directory to the path
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

        yield


# Now safe to import the module under test
import index_core.reparse.validator as validator_module
from index_core.reparse.validator import ReparseValidator, ValidationError


class FakeBlockProcessor:
    """Minimal fake block processor for injecting into compute_block_hashes."""

    def __init__(self):
        """Initialize fake block processor."""
        self.valid_stamps_in_block = []
        self.processed_src20_in_block = []
        self.processed_src721_in_block = []
        self.processed_src101_in_block = []
        self.ledger_updates = {}
        self.collection_operations = []


def test_compute_block_hashes(monkeypatch, tmp_path):
    block_index = 1
    # Initialize validator with dummy snapshot path
    rv = ReparseValidator(snapshot_path=str(tmp_path / "snap.json"))
    # Stub external dependencies
    monkeypatch.setattr(validator_module.backend_instance, "getblockhash", lambda idx: "BHash")
    monkeypatch.setattr(validator_module.backend_instance, "getblock", lambda bh, verbosity: {"time": 100})
    monkeypatch.setattr(validator_module, "fetch_xcp_blocks_concurrent", lambda start, end: {block_index: {"issuances": []}})
    monkeypatch.setattr(
        validator_module,
        "filter_block_transactions",
        lambda block_data, stamp_issuances: (["tx1", "tx2"], {"tx1": {}, "tx2": {}}),
    )
    # Monkey-patch create_check_hashes to return controlled values
    monkeypatch.setattr(
        validator_module,
        "create_check_hashes",
        lambda db, bi, vsib, v20, txlist, plh, ptlh, pms: ("ledger", "txlist", "messages"),
    )
    # Provide fake previous hashes in snapshot
    rv.snapshot_manager._hashes = {
        "hashes": {str(block_index - 1): {"ledger_hash": "pl", "txlist_hash": "pt", "messages_hash": "pm"}}
    }
    # Use fake block processor to bypass real BlockProcessor
    fake_bp = FakeBlockProcessor()
    result = rv.compute_block_hashes(block_index, block_processor=fake_bp)
    # Verify result matches stubbed hash values
    assert result == {
        "block_hash": "BHash",
        "ledger_hash": "ledger",
        "txlist_hash": "txlist",
        "messages_hash": "messages",
    }


def test_validate_block(monkeypatch, tmp_path):
    block_index = 2
    rv = ReparseValidator(snapshot_path=str(tmp_path / "snap.json"))
    # Prepare expected hashes in snapshot
    expected = {"messages_hash": "m", "txlist_hash": "t", "ledger_hash": "l"}
    rv.snapshot_manager._hashes = {"hashes": {str(block_index): expected}}
    # Stub compute_block_hashes to return matching hashes
    monkeypatch.setattr(rv, "compute_block_hashes", lambda idx: {"block_hash": "B", **expected})
    # Should validate successfully
    assert rv.validate_block(block_index)
    # Stub compute_block_hashes to return a mismatch
    monkeypatch.setattr(
        rv,
        "compute_block_hashes",
        lambda idx: {"block_hash": "B", "messages_hash": "X", "txlist_hash": "t", "ledger_hash": "l"},
    )
    assert not rv.validate_block(block_index)
    # Missing expected hashes should raise ValidationError
    rv.snapshot_manager._hashes = {"hashes": {}}
    with pytest.raises(ValidationError):
        rv.validate_block(block_index)
