"""Unit tests for index_core.bootstrap_importer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from index_core import bootstrap_importer

# -----------------------------------------------------------------------------
# is_enabled() — env-var gating
# -----------------------------------------------------------------------------


def test_is_enabled_false_when_neither_set(monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_ON_EMPTY", raising=False)
    monkeypatch.delenv("BOOTSTRAP_FILE", raising=False)
    assert bootstrap_importer.is_enabled() is False


def test_is_enabled_false_when_only_flag_set(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ON_EMPTY", "true")
    monkeypatch.delenv("BOOTSTRAP_FILE", raising=False)
    assert bootstrap_importer.is_enabled() is False


def test_is_enabled_false_when_only_file_set(monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_ON_EMPTY", raising=False)
    monkeypatch.setenv("BOOTSTRAP_FILE", "/tmp/x.sql.zst")
    assert bootstrap_importer.is_enabled() is False


def test_is_enabled_true_when_both_set(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ON_EMPTY", "true")
    monkeypatch.setenv("BOOTSTRAP_FILE", "/tmp/x.sql.zst")
    assert bootstrap_importer.is_enabled() is True


def test_is_enabled_respects_truthy_values(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_FILE", "/tmp/x.sql.zst")
    for v in ("true", "True", "TRUE", "1", "yes"):
        monkeypatch.setenv("BOOTSTRAP_ON_EMPTY", v)
        assert bootstrap_importer.is_enabled() is True, f"failed for {v!r}"
    for v in ("false", "0", "no", "off", ""):
        monkeypatch.setenv("BOOTSTRAP_ON_EMPTY", v)
        assert bootstrap_importer.is_enabled() is False, f"failed for {v!r}"


# -----------------------------------------------------------------------------
# _is_db_empty — empty / non-empty / missing-table
# -----------------------------------------------------------------------------


def _mock_db_with_cursor(rows_for_calls):
    """Build a mock DB whose cursor.fetchone() returns successive values."""
    db = MagicMock()
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchone.side_effect = rows_for_calls
    db.cursor.return_value = cursor
    return db


def test_is_db_empty_true_when_blocks_table_missing():
    db = _mock_db_with_cursor([(0,)])  # information_schema query returns 0
    assert bootstrap_importer._is_db_empty(db) is True


def test_is_db_empty_true_when_blocks_table_empty():
    db = _mock_db_with_cursor([(1,), None])  # table exists; SELECT 1 returns no row
    assert bootstrap_importer._is_db_empty(db) is True


def test_is_db_empty_false_when_blocks_has_rows():
    db = _mock_db_with_cursor([(1,), (1,)])  # table exists; SELECT 1 returns a row
    assert bootstrap_importer._is_db_empty(db) is False


def test_is_db_empty_safe_default_on_error(caplog):
    """If we can't tell, treat as not-empty to avoid clobbering data."""
    import pymysql

    db = MagicMock()
    db.cursor.side_effect = pymysql.Error("simulated")
    with caplog.at_level("WARNING"):
        assert bootstrap_importer._is_db_empty(db) is False
    assert any("empty-check failed" in r.message for r in caplog.records)


# -----------------------------------------------------------------------------
# _validate_bootstrap_file
# -----------------------------------------------------------------------------


def test_validate_rejects_missing_file(tmp_path):
    missing = str(tmp_path / "nope.sql.zst")
    with pytest.raises(bootstrap_importer.BootstrapError, match="not found"):
        bootstrap_importer._validate_bootstrap_file(missing)


def test_validate_rejects_too_small(tmp_path):
    f = tmp_path / "tiny.sql.zst"
    f.write_bytes(b"too small")
    with pytest.raises(bootstrap_importer.BootstrapError, match="suspiciously small"):
        bootstrap_importer._validate_bootstrap_file(str(f))


def test_validate_rejects_bad_suffix(tmp_path):
    f = tmp_path / "bundle.tar"
    f.write_bytes(b"x" * 2048)
    with pytest.raises(bootstrap_importer.BootstrapError, match="must end in .sql"):
        bootstrap_importer._validate_bootstrap_file(str(f))


def test_validate_accepts_well_formed_file(tmp_path):
    f = tmp_path / "bootstrap.sql.zst"
    f.write_bytes(b"x" * 2048)
    bootstrap_importer._validate_bootstrap_file(str(f))  # no raise


def test_validate_rejects_empty_path():
    with pytest.raises(bootstrap_importer.BootstrapError, match="not set"):
        bootstrap_importer._validate_bootstrap_file("")


# -----------------------------------------------------------------------------
# _verify_against_checkpoints
# -----------------------------------------------------------------------------


@patch("index_core.bootstrap_importer.CHECKPOINTS_MAINNET", new=None, create=True)
def test_verify_raises_on_missing_checkpoint_block():
    # Build a DB where max_block=790000 but checkpoint at 779700 is missing
    db = MagicMock()
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor

    # First call (MAX(block_index)) returns 790000
    # Subsequent SELECT for checkpoint returns None
    cursor.fetchone.side_effect = [(790000,), None]
    db.cursor.return_value = cursor

    with patch.object(
        bootstrap_importer,
        "_verify_against_checkpoints",
        wraps=bootstrap_importer._verify_against_checkpoints,
    ):
        # We need a real CHECKPOINTS_MAINNET shape for the test
        with patch("index_core.check.CHECKPOINTS_MAINNET", {779700: {"txlist_hash": "abc", "ledger_hash": ""}}):
            with pytest.raises(bootstrap_importer.BootstrapError, match="missing from imported bootstrap"):
                bootstrap_importer._verify_against_checkpoints(db)


def test_verify_raises_on_txlist_hash_mismatch():
    db = MagicMock()
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchone.side_effect = [(790000,), ("WRONG_HASH", "")]
    db.cursor.return_value = cursor

    with patch(
        "index_core.check.CHECKPOINTS_MAINNET",
        {779700: {"txlist_hash": "expected_txlist_hash", "ledger_hash": ""}},
    ):
        with pytest.raises(bootstrap_importer.BootstrapError, match="txlist_hash mismatch"):
            bootstrap_importer._verify_against_checkpoints(db)


def test_verify_skips_checkpoints_beyond_max_block():
    """A partial bootstrap (e.g. through block 796,000) shouldn't fail
    just because CHECKPOINTS_MAINNET has entries past that point."""
    db = MagicMock()
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    # max_block=790000 ; checkpoint at 779700 matches, at 800000 should be skipped
    cursor.fetchone.side_effect = [(790000,), ("hash_779700", "")]
    db.cursor.return_value = cursor

    with patch(
        "index_core.check.CHECKPOINTS_MAINNET",
        {
            779700: {"txlist_hash": "hash_779700", "ledger_hash": ""},
            800000: {"txlist_hash": "hash_800000", "ledger_hash": ""},
        },
    ):
        checked, max_block = bootstrap_importer._verify_against_checkpoints(db)
        assert checked == 1
        assert max_block == 790000


# -----------------------------------------------------------------------------
# maybe_import — orchestration
# -----------------------------------------------------------------------------


def test_maybe_import_skips_when_not_enabled(monkeypatch, caplog):
    monkeypatch.delenv("BOOTSTRAP_ON_EMPTY", raising=False)
    monkeypatch.delenv("BOOTSTRAP_FILE", raising=False)
    db = MagicMock()
    with caplog.at_level("DEBUG"):
        assert bootstrap_importer.maybe_import(db) is False


def test_maybe_import_skips_when_db_not_empty(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ON_EMPTY", "true")
    monkeypatch.setenv("BOOTSTRAP_FILE", "/tmp/anything.sql.zst")
    db = _mock_db_with_cursor([(1,), (1,)])
    assert bootstrap_importer.maybe_import(db) is False


def test_maybe_import_runs_full_flow_on_empty_db(monkeypatch, tmp_path):
    f = tmp_path / "bootstrap.sql.zst"
    f.write_bytes(b"x" * 2048)
    monkeypatch.setenv("BOOTSTRAP_ON_EMPTY", "true")
    monkeypatch.setenv("BOOTSTRAP_FILE", str(f))

    db = _mock_db_with_cursor([(0,), (790000,), ("hash_779700", "")])
    with patch.object(bootstrap_importer, "_import_sql") as mock_import, patch(
        "index_core.check.CHECKPOINTS_MAINNET",
        {779700: {"txlist_hash": "hash_779700", "ledger_hash": ""}},
    ):
        assert bootstrap_importer.maybe_import(db) is True
        mock_import.assert_called_once_with(str(f))


# -----------------------------------------------------------------------------
# run_or_exit — translates BootstrapError to sys.exit(5)
# -----------------------------------------------------------------------------


def test_run_or_exit_uses_distinct_exit_code(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ON_EMPTY", "true")
    monkeypatch.setenv("BOOTSTRAP_FILE", "/nonexistent/file.sql.zst")
    db = _mock_db_with_cursor([(0,)])  # empty → flow proceeds to file validation → fail
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_importer.run_or_exit(db)
    assert excinfo.value.code == bootstrap_importer.EXIT_CODE_BOOTSTRAP_FAILURE


def test_run_or_exit_silent_when_disabled(monkeypatch):
    """No env vars → no-op, no SystemExit raised."""
    monkeypatch.delenv("BOOTSTRAP_ON_EMPTY", raising=False)
    monkeypatch.delenv("BOOTSTRAP_FILE", raising=False)
    db = MagicMock()
    bootstrap_importer.run_or_exit(db)  # should return normally
