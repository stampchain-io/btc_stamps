import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest

### Stub external dependencies before importing project modules
### Use Any typing to suppress mypy attr-defined errors
# Stub boto3 for config imports
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
# Stub bitcoin module for index_core.util imports
_btc_mod: Any = types.ModuleType("bitcoin")
sys.modules["bitcoin"] = _btc_mod
_btc_wallet: Any = types.ModuleType("bitcoin.wallet")
_btc_wallet.CBitcoinAddress = lambda addr: addr
sys.modules["bitcoin.wallet"] = _btc_wallet
# Stub bitcoinlib module for index_core.util imports
_blib_mod: Any = types.ModuleType("bitcoinlib")
sys.modules["bitcoinlib"] = _blib_mod
_blib_encoding: Any = types.ModuleType("bitcoinlib.encoding")
_blib_encoding.addr_bech32_to_pubkeyhash = lambda addr: None
_blib_encoding.addr_base58_to_pubkeyhash = lambda addr: None
sys.modules["bitcoinlib.encoding"] = _blib_encoding
# Stub ecdsa module for index_core.util imports
_ecdsa_mod: Any = types.ModuleType("ecdsa")
_ecdsa_mod.SECP256k1 = object


class _VerifyingKey:
    pass


_ecdsa_mod.VerifyingKey = _VerifyingKey
sys.modules["ecdsa"] = _ecdsa_mod
# Stub psutil module for index_core.memory_manager imports
_psutil_mod: Any = types.ModuleType("psutil")
# Provide Process to avoid attribute errors
_psutil_mod.Process = lambda pid: types.SimpleNamespace(memory_info=lambda: None)
sys.modules["psutil"] = _psutil_mod
_blocks_mod: Any = types.ModuleType("index_core.blocks")
_blocks_mod.BlockProcessor = lambda db: None
_blocks_mod.backend_instance = types.SimpleNamespace(getblockhash=lambda idx: None, getblock=lambda *args, **kwargs: {})
_blocks_mod.create_check_hashes = lambda *args, **kwargs: (None, None, None)
_blocks_mod.fetch_xcp_blocks_concurrent = lambda *args, **kwargs: {}
_blocks_mod.filter_block_transactions = lambda *args, **kwargs: ([], {})
_blocks_mod.process_tx = lambda *args, **kwargs: types.SimpleNamespace(data=None, tx_hash=None, _replace=lambda **kw: None)
sys.modules["index_core.blocks"] = _blocks_mod

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
import index_core.reparse.validator as validator_module
from index_core.reparse.validator import ReparseValidator, ValidationError


class FakeBlockProcessor:
    """Minimal fake block processor for injecting into compute_block_hashes."""

    def __init__(self):
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
