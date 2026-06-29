"""Tests for the optional file-based inline validation mode (reference_hashes.json).

Consensus-NEUTRAL: exercises validation tooling only; it does NOT touch the
indexer's decode/parse/hash logic. All DB access is mocked — no real DB or
network is used.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config
from index_core import block_validation

# Small in-memory reference map mirroring snapshots/reference_hashes.json's
# "hashes" shape. ledger_hash is "" for the genesis-era style entry.
REFERENCE = {
    "1000": {
        "block_hash": "bh1000",
        "ledger_hash": "",
        "messages_hash": "mh1000",
        "txlist_hash": "th1000",
    },
}


@pytest.fixture(autouse=True)
def _seed_reference_cache():
    """Seed the module-level reference cache so no file is read, and restore it."""
    original = block_validation._REFERENCE_HASHES_CACHE
    block_validation._REFERENCE_HASHES_CACHE = dict(REFERENCE)
    yield
    block_validation._REFERENCE_HASHES_CACHE = original


def _row(**overrides):
    base = {
        "block_hash": "bh1000",
        "ledger_hash": "",
        "txlist_hash": "th1000",
        "messages_hash": "mh1000",
    }
    base.update(overrides)
    return base


def test_match_returns_true():
    with patch.object(block_validation, "_read_block_hashes", return_value=_row()):
        assert block_validation.validate_block_against_reference(1000) is True


def test_mismatch_returns_false():
    with patch.object(block_validation, "_read_block_hashes", return_value=_row(txlist_hash="WRONG")):
        assert block_validation.validate_block_against_reference(1000) is False


def test_missing_block_returns_true_with_warning(caplog):
    # Block 2000 is not present in the reference file -> non-fatal True + warning,
    # and the DB is never queried (short-circuits before _read_block_hashes).
    with patch.object(block_validation, "_read_block_hashes") as read_mock:
        with caplog.at_level("WARNING", logger="validate_block"):
            result = block_validation.validate_block_against_reference(2000)
    assert result is True
    read_mock.assert_not_called()
    assert any("not present in reference_hashes.json" in r.message for r in caplog.records)


def test_block_absent_from_db_returns_true():
    # Block is in the reference file but missing from the dev DB -> non-fatal True.
    with patch.object(block_validation, "_read_block_hashes", return_value=None):
        assert block_validation.validate_block_against_reference(1000) is True


def test_dispatcher_default_mode_uses_db_unchanged():
    """Default VALIDATION_MODE 'db' must call ONLY the compare_tables path."""
    original_mode = getattr(config, "VALIDATION_MODE", "db")
    config.VALIDATION_MODE = "db"
    config.DEBUG_VALIDATION = True
    try:
        with patch.object(block_validation, "_validate_block_against_production_db", return_value=True) as db_mock:
            with patch.object(block_validation, "validate_block_against_reference") as ref_mock:
                assert block_validation.validate_block_against_production(5000) is True
        db_mock.assert_called_once_with(5000)
        ref_mock.assert_not_called()
    finally:
        config.VALIDATION_MODE = original_mode
        config.DEBUG_VALIDATION = False


def test_dispatcher_reference_mode_uses_reference_only():
    original_mode = getattr(config, "VALIDATION_MODE", "db")
    config.VALIDATION_MODE = "reference"
    config.DEBUG_VALIDATION = True
    try:
        with patch.object(block_validation, "_validate_block_against_production_db") as db_mock:
            with patch.object(block_validation, "validate_block_against_reference", return_value=True) as ref_mock:
                assert block_validation.validate_block_against_production(5000) is True
        db_mock.assert_not_called()
        ref_mock.assert_called_once_with(5000)
    finally:
        config.VALIDATION_MODE = original_mode
        config.DEBUG_VALIDATION = False


def test_dispatcher_both_mode_ands_results():
    original_mode = getattr(config, "VALIDATION_MODE", "db")
    config.VALIDATION_MODE = "both"
    config.DEBUG_VALIDATION = True
    try:
        with patch.object(block_validation, "_validate_block_against_production_db", return_value=True):
            with patch.object(block_validation, "validate_block_against_reference", return_value=False):
                assert block_validation.validate_block_against_production(5000) is False
    finally:
        config.VALIDATION_MODE = original_mode
        config.DEBUG_VALIDATION = False
