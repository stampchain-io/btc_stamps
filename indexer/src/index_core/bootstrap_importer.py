"""Bootstrap import path for partner-distributed DB snapshots.

When ``BOOTSTRAP_ON_EMPTY=true`` and ``BOOTSTRAP_FILE=/path/to/bootstrap.sql.zst``
are both set, the indexer will — on first startup against an empty
``btc_stamps`` schema — decompress + ``mysql``-import the bundled SQL,
then verify the resulting DB state against ``CHECKPOINTS_MAINNET`` and
abort hard on any mismatch.

Design notes:
- Opt-in only. Without ``BOOTSTRAP_ON_EMPTY=true`` this module is inert.
- Idempotent: an already-populated DB short-circuits before any work.
- Fail-hard on mismatch with a distinct exit code so systemd doesn't
  flap-restart a corrupted DB.
- Decompress + import is streamed via stdin pipes to ``mysql``; no
  multi-GB intermediate temp file.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Tuple

import pymysql
from pymysql.connections import Connection

logger = logging.getLogger(__name__)


# Distinct exit code for systemd: "configuration / data error, don't
# auto-restart". Matches the codes used in critical_failure_handler.py
# (2=DB, 3=consensus, 4=rollback-loop) so 5 is the next available slot.
EXIT_CODE_BOOTSTRAP_FAILURE = 5


class BootstrapError(RuntimeError):
    """Raised when the import or post-import validation fails."""


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("true", "1", "yes")


def is_enabled() -> bool:
    """Return True when both gating env vars are set."""
    return _env_truthy("BOOTSTRAP_ON_EMPTY") and bool(os.environ.get("BOOTSTRAP_FILE", "").strip())


def _is_db_empty(db: Connection) -> bool:
    """True when the ``blocks`` table has no rows (or doesn't exist).

    The ``blocks`` table is the canonical block-record table — empty
    means a clean schema with no historical data. We can't use any
    other table because the import will populate them all.
    """
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables " "WHERE table_schema = DATABASE() AND table_name = 'blocks'"
            )
            row = cursor.fetchone()
            if not row or row[0] == 0:
                return True  # table doesn't exist yet
            cursor.execute("SELECT 1 FROM blocks LIMIT 1")
            return cursor.fetchone() is None
    except pymysql.MySQLError as e:
        logger.warning(f"bootstrap_importer: empty-check failed ({e}); treating as not-empty (safe default)")
        return False


def _validate_bootstrap_file(path: str) -> None:
    """Sanity-check the bootstrap artifact before doing anything destructive."""
    if not path:
        raise BootstrapError("BOOTSTRAP_FILE is not set")
    if not os.path.isfile(path):
        raise BootstrapError(f"BOOTSTRAP_FILE not found: {path}")
    if not os.access(path, os.R_OK):
        raise BootstrapError(f"BOOTSTRAP_FILE not readable: {path}")
    if not path.endswith(".sql.zst") and not path.endswith(".sql"):
        raise BootstrapError(f"BOOTSTRAP_FILE must end in .sql or .sql.zst: {path}")
    size = os.path.getsize(path)
    if size < 1024:
        raise BootstrapError(f"BOOTSTRAP_FILE suspiciously small ({size} bytes): {path}")
    logger.info(f"bootstrap_importer: artifact OK — {path} ({size / (1024**2):.1f} MB)")


def _import_sql(path: str) -> None:
    """Stream the (optionally-zstd-compressed) SQL into ``mysql`` via pipes.

    Uses the same DB credentials the indexer's pool was built with so
    we don't need a second credentials source.
    """
    from index_core import database_manager

    params = database_manager.DatabaseManager().get_connection_params()
    mysql_argv = [
        "mysql",
        f"--host={params['host']}",
        f"--port={params['port']}",
        f"--user={params['user']}",
        f"--password={params['password']}",
        "--default-character-set=utf8mb4",
        params["database"],
    ]

    if path.endswith(".sql.zst"):
        # zstdcat <file> | mysql ...
        decompress = subprocess.Popen(["zstdcat", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        importer = subprocess.Popen(mysql_argv, stdin=decompress.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if decompress.stdout:
            decompress.stdout.close()  # let SIGPIPE propagate if importer dies
        imp_out, imp_err = importer.communicate()
        _, dec_err = decompress.communicate()
        if decompress.returncode != 0:
            raise BootstrapError(f"zstdcat failed (rc={decompress.returncode}): {dec_err.decode('utf-8', 'replace')[:500]}")
        if importer.returncode != 0:
            raise BootstrapError(f"mysql import failed (rc={importer.returncode}): {imp_err.decode('utf-8', 'replace')[:500]}")
    else:
        with open(path, "rb") as f:
            importer = subprocess.Popen(mysql_argv, stdin=f, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            imp_out, imp_err = importer.communicate()
        if importer.returncode != 0:
            raise BootstrapError(f"mysql import failed (rc={importer.returncode}): {imp_err.decode('utf-8', 'replace')[:500]}")

    logger.info("bootstrap_importer: SQL import completed successfully")


def _verify_against_checkpoints(db: Connection) -> Tuple[int, int]:
    """Compare imported ``blocks`` rows to ``CHECKPOINTS_MAINNET``.

    Returns (checked, max_block_in_db). Raises BootstrapError on any
    mismatch — we refuse to start on a suspect bootstrap rather than
    silently accept it and corrupt downstream state.
    """
    from index_core.check import CHECKPOINTS_MAINNET

    with db.cursor() as cursor:
        cursor.execute("SELECT MAX(block_index) FROM blocks")
        row = cursor.fetchone()
        max_block = int(row[0]) if row and row[0] is not None else 0

    checked = 0
    with db.cursor() as cursor:
        for block_index, expected in sorted(CHECKPOINTS_MAINNET.items()):
            if block_index > max_block:
                continue  # checkpoint beyond bootstrap end — fine, we just imported a partial chain
            cursor.execute(
                "SELECT txlist_hash, ledger_hash FROM blocks WHERE block_index = %s",
                (block_index,),
            )
            row = cursor.fetchone()
            if row is None:
                raise BootstrapError(
                    f"checkpoint block {block_index} missing from imported bootstrap " f"(max_block={max_block})"
                )
            actual_txlist, actual_ledger = row
            if expected["txlist_hash"] and actual_txlist != expected["txlist_hash"]:
                raise BootstrapError(
                    f"txlist_hash mismatch at block {block_index}: " f"expected {expected['txlist_hash']}, got {actual_txlist}"
                )
            if expected.get("ledger_hash") and actual_ledger != expected["ledger_hash"]:
                raise BootstrapError(
                    f"ledger_hash mismatch at block {block_index}: " f"expected {expected['ledger_hash']}, got {actual_ledger}"
                )
            checked += 1

    return checked, max_block


def maybe_import(db: Connection) -> bool:
    """Entry point. Returns True if an import ran, False if skipped.

    Raises BootstrapError on any failure — the caller is expected to
    surface this as a fatal, non-restartable exit.
    """
    if not is_enabled():
        logger.debug("bootstrap_importer: not enabled (BOOTSTRAP_ON_EMPTY/BOOTSTRAP_FILE unset)")
        return False

    if not _is_db_empty(db):
        logger.info(
            "bootstrap_importer: DB is non-empty, skipping import "
            "(BOOTSTRAP_ON_EMPTY is intentionally a no-op when data exists)"
        )
        return False

    bootstrap_file = os.environ["BOOTSTRAP_FILE"].strip()
    logger.warning("=" * 72)
    logger.warning(f"bootstrap_importer: empty DB detected — beginning import from {bootstrap_file}")
    logger.warning("=" * 72)

    _validate_bootstrap_file(bootstrap_file)
    _import_sql(bootstrap_file)

    checked, max_block = _verify_against_checkpoints(db)
    logger.warning(
        f"bootstrap_importer: validated {checked} checkpoints against imported state "
        f"(max_block={max_block}). Import accepted."
    )
    return True


def run_or_exit(db: Connection) -> None:
    """Convenience wrapper for the indexer startup path.

    Calls ``maybe_import()`` and translates any BootstrapError into a
    clean process exit with ``EXIT_CODE_BOOTSTRAP_FAILURE``, so systemd
    treats it as a config error rather than a crash worth restarting.
    """
    try:
        maybe_import(db)
    except BootstrapError as e:
        logger.critical(f"bootstrap_importer: FATAL — {e}")
        logger.critical(
            "bootstrap_importer: refusing to start on a suspect bootstrap. "
            "Either remove BOOTSTRAP_ON_EMPTY / BOOTSTRAP_FILE to skip import, "
            "or replace BOOTSTRAP_FILE with a verified artifact."
        )
        sys.exit(EXIT_CODE_BOOTSTRAP_FAILURE)
    except Exception as e:  # noqa: BLE001 — really want to catch everything in this path
        logger.critical(f"bootstrap_importer: unexpected error during import: {e}", exc_info=True)
        sys.exit(EXIT_CODE_BOOTSTRAP_FAILURE)
