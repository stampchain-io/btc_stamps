"""Unit tests for indexer/tools/refresh_reference_hashes.py.

Covers the pure-Python helpers (snapshot diff, atomic write, AST checkpoint
parser, snapshot file shape preservation). End-to-end DB integration is
exercised by hand against the operator's dev DB; not appropriate for CI.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest


def _load():
    here = Path(__file__).resolve().parent
    path = here.parent / "tools" / "refresh_reference_hashes.py"
    spec = importlib.util.spec_from_file_location("refresh_reference_hashes", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["refresh_reference_hashes"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_summarize_diff_counts_added_modified_removed():
    m = _load()
    existing = {
        "100": {"block_hash": "a", "messages_hash": "x", "txlist_hash": "y", "ledger_hash": ""},
        "101": {"block_hash": "b", "messages_hash": "x", "txlist_hash": "y", "ledger_hash": ""},
    }
    new = {
        "100": {"block_hash": "a", "messages_hash": "x", "txlist_hash": "y", "ledger_hash": ""},
        "101": {"block_hash": "b-MODIFIED", "messages_hash": "x", "txlist_hash": "y", "ledger_hash": ""},
        "102": {"block_hash": "c", "messages_hash": "x", "txlist_hash": "y", "ledger_hash": ""},
    }
    added, modified, removed = m._summarize_diff(existing, new)
    assert added == 1 and modified == 1 and removed == 0


def test_load_existing_handles_wrapped_shape(tmp_path):
    """Today's on-disk format is {"metadata": {}, "hashes": {...}}."""
    m = _load()
    path = tmp_path / "ref.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {"source": "test"},
                "hashes": {"100": {"block_hash": "a", "messages_hash": "", "txlist_hash": "", "ledger_hash": ""}},
            }
        )
    )
    hashes, meta = m._load_existing(path)
    assert hashes == {"100": {"block_hash": "a", "messages_hash": "", "txlist_hash": "", "ledger_hash": ""}}
    assert meta == {"source": "test"}


def test_load_existing_handles_flat_shape(tmp_path):
    """Older / hand-built files may be a flat block_index → entry map."""
    m = _load()
    path = tmp_path / "ref.json"
    path.write_text(json.dumps({"100": {"block_hash": "a", "messages_hash": "", "txlist_hash": "", "ledger_hash": ""}}))
    hashes, meta = m._load_existing(path)
    assert "100" in hashes
    assert meta == {}


def test_load_existing_returns_empty_for_missing(tmp_path):
    m = _load()
    hashes, meta = m._load_existing(tmp_path / "does_not_exist.json")
    assert hashes == {} and meta == {}


def test_atomic_write_is_atomic_on_failure(tmp_path):
    """Even if json.dump succeeds, a crash before rename must leave the
    target untouched. We can't easily simulate the crash, but we can
    verify no `.tmp` files are left behind on success."""
    m = _load()
    path = tmp_path / "ref.json"
    m._atomic_write(path, {"hashes": {"1": {"block_hash": "a"}}, "metadata": {}})
    assert path.exists()
    # No stale tmp files
    tmp_files = [p for p in tmp_path.iterdir() if p.name != "ref.json"]
    assert tmp_files == []
    # Round-trip
    assert json.loads(path.read_text())["hashes"] == {"1": {"block_hash": "a"}}


def test_wrap_for_writing_preserves_metadata():
    m = _load()
    out = m._wrap_for_writing({"100": {"block_hash": "a"}}, {"source": "abc"})
    assert out == {"metadata": {"source": "abc"}, "hashes": {"100": {"block_hash": "a"}}}


def test_eval_checkpoints_skips_nonliteral_keys(tmp_path):
    """The real check.py uses `config.CP_STAMP_GENESIS_BLOCK` as one key
    (an Attribute, not an int literal). The parser must skip it gracefully,
    not crash."""
    m = _load()
    fake = tmp_path / "check.py"
    fake.write_text(textwrap.dedent("""
        import config

        CHECKPOINTS_MAINNET = {
            config.CP_STAMP_GENESIS_BLOCK: {"ledger_hash": "", "txlist_hash": "genesis"},
            779700: {"ledger_hash": "L1", "txlist_hash": "T1"},
            780000: {"ledger_hash": "L2", "txlist_hash": "T2"},
        }
    """))
    out = m._read_checkpoints_from_source(fake)
    # The genesis-via-attribute entry should be skipped; the two literal
    # entries should be present.
    assert set(out.keys()) == {779700, 780000}
    assert out[779700]["txlist_hash"] == "T1"


def test_validate_against_checkpoints_passes_when_match(tmp_path):
    m = _load()
    snapshot = {
        "779700": {"block_hash": "a", "messages_hash": "x", "txlist_hash": "T1", "ledger_hash": "L1"},
    }
    checkpoints = {779700: {"ledger_hash": "L1", "txlist_hash": "T1"}}
    # No exception → pass
    m._validate_against_checkpoints(snapshot, checkpoints)


def test_validate_against_checkpoints_fails_on_mismatch():
    m = _load()
    snapshot = {
        "779700": {"block_hash": "a", "messages_hash": "x", "txlist_hash": "DRIFTED", "ledger_hash": "L1"},
    }
    checkpoints = {779700: {"ledger_hash": "L1", "txlist_hash": "T1"}}
    with pytest.raises(SystemExit) as exc_info:
        m._validate_against_checkpoints(snapshot, checkpoints)
    assert "Checkpoint validation FAILED" in str(exc_info.value)
    assert "txlist_hash" in str(exc_info.value)


def test_validate_against_checkpoints_fails_on_missing_block():
    m = _load()
    snapshot = {}  # snapshot empty
    checkpoints = {779700: {"ledger_hash": "L1", "txlist_hash": "T1"}}
    with pytest.raises(SystemExit, match="MISSING"):
        m._validate_against_checkpoints(snapshot, checkpoints)


def test_validate_skips_empty_checkpoint_fields():
    """Some CHECKPOINTS_MAINNET entries have empty ledger_hash (early blocks
    pre-SRC-20). Empty expected value means 'don't check this field'."""
    m = _load()
    snapshot = {"779700": {"block_hash": "a", "messages_hash": "", "txlist_hash": "T1", "ledger_hash": "ANY"}}
    checkpoints = {779700: {"ledger_hash": "", "txlist_hash": "T1"}}  # empty ledger_hash
    # Should not raise — empty checkpoint value is "don't check"
    m._validate_against_checkpoints(snapshot, checkpoints)


# --- Source-of-truth guard (issue #814) -------------------------------------


def test_verify_mode_is_exempt_from_source_confirmation():
    """verify is read-only; it must never require --confirm-source-host."""
    m = _load()
    # No confirmation passed, any host — must not raise.
    m._require_confirmed_source("verify", "127.0.0.1", None)


@pytest.mark.parametrize("mode", ["extend", "rebuild"])
def test_write_mode_aborts_without_confirmation(mode):
    m = _load()
    with pytest.raises(SystemExit) as exc:
        m._require_confirmed_source(mode, "dev-mysql.local", None)
    msg = str(exc.value)
    assert "refusing to write reference_hashes.json" in msg
    # The resolved host must be named so the operator can copy it.
    assert "dev-mysql.local" in msg
    assert "--confirm-source-host dev-mysql.local" in msg


@pytest.mark.parametrize("mode", ["extend", "rebuild"])
def test_write_mode_aborts_on_mismatched_confirmation(mode):
    m = _load()
    with pytest.raises(SystemExit) as exc:
        m._require_confirmed_source(mode, "prod-rds.example.com", "wrong-host")
    assert "prod-rds.example.com" in str(exc.value)


@pytest.mark.parametrize("mode", ["extend", "rebuild"])
def test_write_mode_accepts_matching_confirmation(mode):
    m = _load()
    # Matching host → no exception → proceed.
    m._require_confirmed_source(mode, "prod-rds.example.com", "prod-rds.example.com")
