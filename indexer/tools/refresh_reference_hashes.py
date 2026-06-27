#!/usr/bin/env python3
"""Refresh indexer/snapshots/reference_hashes.json from a btc_stamps DB.

`reference_hashes.json` is the canonical replay baseline (one entry per block
from CP_STAMP_GENESIS_BLOCK to whatever the operator's DB has indexed) used by
the reparse validator and the Tier 1 CI runner. Without this script, the file
drifts behind the chain tip — today's checked-in baseline stops at 892,905
even though chain tip is ~955,000.

Three modes:

  extend (default)
    Read the existing file. Connect to the DB. For each block_index in the DB
    NOT already in the file, append a new entry. Preserves existing entries
    even if the DB's value for them differs (defensive: we trust the
    historically-validated snapshot over a potentially-stale DB).

  rebuild
    Ignore the existing file. Walk the entire DB from genesis to tip, writing
    every entry. Use only after a known-good reindex (e.g. after a consensus
    PR like #753 has been fully validated to chain tip).

  verify
    Read-only. Compare the existing file against the DB. Report any blocks in
    one but not the other, and any rows where the hashes disagree. Useful
    pre-flight check before an extend/rebuild.

All modes:
  - Cross-validate the resulting in-memory snapshot against
    indexer/src/index_core/check.py:CHECKPOINTS_MAINNET. Abort on mismatch.
  - Write to a `.tmp` file first, then atomic rename. No half-written state.
  - Print a diff summary before writing.

DB connection: reads stamps DB creds from env (RDS_HOSTNAME / RDS_USER /
RDS_PASSWORD / RDS_DATABASE) or from a `--db-host` CLI flag. Refuses to run if
neither is configured — accidental "where does it point?" runs are bad.

SOURCE-OF-TRUTH GUARD (write modes only):
  `reference_hashes.json` must ONLY ever be (re)generated from a PROD-validated
  chain state. In the dev tree, RDS_* points at the dev docker MySQL
  (127.0.0.1:3306), so an unconfirmed `extend`/`rebuild` could silently bake a
  wrong baseline from an unvalidated DB. To make "where does it point?"
  impossible to get wrong by accident, `extend` and `rebuild`:
    - print the resolved source DB host prominently before any write, and
    - REFUSE to write unless `--confirm-source-host <host>` matches that host.
  Only confirm a host that holds a prod-validated chain state. A validated dev
  reindex IS a legitimate source: fully reindex dev, `compare_tables.py`-validate
  it against prod with zero divergence, THEN extend from that dev DB (confirming
  its host). `verify` is read-only and unguarded.

Usage examples:

  # Verify current state vs current DB (read-only sanity check, no confirm needed)
  poetry run python tools/refresh_reference_hashes.py --mode verify

  # Extend the baseline forward from chain-tip (after a prod-validated reindex).
  # Must confirm the resolved source host (here: prod RDS).
  poetry run python tools/refresh_reference_hashes.py --mode extend \
      --confirm-source-host prod-rds.example.com

  # Full rebuild (use sparingly — only after intentional consensus correction
  # on a prod-validated source). Must confirm the resolved source host.
  poetry run python tools/refresh_reference_hashes.py --mode rebuild \
      --confirm-source-host prod-rds.example.com
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger("refresh_reference_hashes")


# Block of one of the four hash types we persist. ledger_hash is allowed to
# be the empty string (early blocks predate the SRC-20 ledger), so any field
# that's "" in the source row gets stored as "" in the snapshot — production
# parsers expect this shape.
def _row_to_entry(row: tuple) -> Dict[str, str]:
    block_hash, messages_hash, txlist_hash, ledger_hash = row
    return {
        "block_hash": block_hash,
        "messages_hash": messages_hash or "",
        "txlist_hash": txlist_hash or "",
        "ledger_hash": ledger_hash or "",
    }


def _read_checkpoints_from_source(check_py_path: Path) -> Dict[int, Dict[str, str]]:
    """Parse CHECKPOINTS_MAINNET from indexer/src/index_core/check.py via AST.

    We don't import the module — that pulls in the whole indexer surface
    (DatabaseManager, config, etc.) and is overkill for reading one dict.
    """
    source = check_py_path.read_text()
    tree = ast.parse(source, filename=str(check_py_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "CHECKPOINTS_MAINNET" and isinstance(node.value, ast.Dict):
                return _eval_checkpoints_dict(node.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CHECKPOINTS_MAINNET":
                    if isinstance(node.value, ast.Dict):
                        return _eval_checkpoints_dict(node.value)
    raise RuntimeError(f"CHECKPOINTS_MAINNET not found in {check_py_path}")


def _eval_checkpoints_dict(d: ast.Dict) -> Dict[int, Dict[str, str]]:
    """Parse CHECKPOINTS_MAINNET literal entries.

    Skips entries whose key isn't an int literal — `config.CP_STAMP_GENESIS_BLOCK`
    is one such entry. Genesis doesn't need cross-validation: its ledger_hash
    is empty by definition and its txlist_hash is dictated by config, not by
    the snapshot we're maintaining. The other ~30 entries (literal block
    heights) are what we actually validate against.
    """
    out: Dict[int, Dict[str, str]] = {}
    skipped = 0
    for k_node, v_node in zip(d.keys, d.values):
        if not isinstance(k_node, ast.Constant) or not isinstance(k_node.value, int):
            # Non-literal key (e.g. config.CP_STAMP_GENESIS_BLOCK). Skip.
            skipped += 1
            continue
        if not isinstance(v_node, ast.Dict):
            raise RuntimeError(f"unexpected CHECKPOINTS_MAINNET value shape at key {k_node.value}")
        block_index = int(k_node.value)
        entry: Dict[str, str] = {}
        for sub_k, sub_v in zip(v_node.keys, v_node.values):
            if not isinstance(sub_k, ast.Constant) or not isinstance(sub_v, ast.Constant):
                raise RuntimeError(f"unexpected entry shape at block {block_index}")
            entry[str(sub_k.value)] = str(sub_v.value)
        out[block_index] = entry
    if skipped:
        logger.debug("Skipped %d CHECKPOINTS_MAINNET entries with non-literal keys", skipped)
    return out


def _validate_against_checkpoints(
    snapshot: Dict[str, Dict[str, str]],
    checkpoints: Dict[int, Dict[str, str]],
) -> None:
    """Abort if any CHECKPOINTS_MAINNET entry disagrees with the snapshot.

    Genesis-block checkpoint entries don't appear in CHECKPOINTS_MAINNET at all
    (they live in CP_STAMP_GENESIS_BLOCK config), so missing genesis is fine.
    Every other checkpoint must match.
    """
    failures = []
    for block_index, expected in checkpoints.items():
        key = str(block_index)
        if key not in snapshot:
            failures.append(f"  block {block_index}: in CHECKPOINTS_MAINNET, MISSING from snapshot")
            continue
        actual = snapshot[key]
        for field, expected_value in expected.items():
            if not expected_value:
                continue
            actual_value = actual.get(field, "")
            if actual_value != expected_value:
                failures.append(
                    f"  block {block_index} {field}: snapshot={actual_value[:16]}... " f"checkpoint={expected_value[:16]}..."
                )
    if failures:
        msg = "Checkpoint validation FAILED:\n" + "\n".join(failures)
        raise SystemExit(msg)
    logger.info("Cross-validated %d checkpoint entries against snapshot", len(checkpoints))


def _connect_db(host: str, user: str, password: str, database: str):
    import pymysql

    return pymysql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        connect_timeout=15,
        read_timeout=120,
    )


def _fetch_db_blocks(
    conn,
    start_block: int,
    end_block: Optional[int] = None,
) -> Dict[str, Dict[str, str]]:
    """Pull (block_index, block_hash, messages_hash, txlist_hash, ledger_hash)
    rows from the DB into a snapshot-shaped dict. block_index becomes a str
    key to match the canonical JSON shape on disk."""
    out: Dict[str, Dict[str, str]] = {}
    sql = (
        "SELECT block_index, block_hash, messages_hash, txlist_hash, "
        "IFNULL(ledger_hash,'') FROM blocks WHERE block_index >= %s"
    )
    params: tuple = (start_block,)
    if end_block is not None:
        sql += " AND block_index <= %s"
        params = (start_block, end_block)
    sql += " ORDER BY block_index"

    with conn.cursor() as cur:
        cur.execute(sql, params)
        # Stream rather than buffer the whole result set — 175k rows is
        # ~30MB. pymysql cursors are buffered by default; that's fine for
        # this scale (peak ~50MB RSS).
        for row in cur.fetchall():
            block_index = row[0]
            out[str(block_index)] = _row_to_entry(row[1:])
    return out


def _load_existing(path: Path) -> Tuple[Dict[str, Dict[str, str]], Dict[str, object]]:
    """Return (hashes, metadata). Snapshot on disk is `{"metadata": {}, "hashes": {...}}`.
    Older or hand-built files may be a flat map; we tolerate both."""
    if not path.exists():
        return {}, {}
    with path.open() as f:
        data = json.load(f)
    if isinstance(data, dict) and "hashes" in data and isinstance(data["hashes"], dict):
        meta = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
        return data["hashes"], meta
    # Fall-through: flat block_index → entry map. No metadata.
    return data, {}


def _wrap_for_writing(hashes: Dict[str, Dict[str, str]], metadata: Dict[str, object]) -> Dict[str, object]:
    # Preserve the on-disk shape `{"metadata": ..., "hashes": ...}` that
    # SnapshotManager.load_snapshot expects.
    return {"metadata": metadata or {}, "hashes": hashes}


def _atomic_write(path: Path, data: Dict[str, Dict[str, str]]) -> None:
    """Write to .tmp + fsync + rename. Survives a kill mid-write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=str(path.parent), prefix=path.name + ".", suffix=".tmp", delete=False
    ) as tmp:
        json.dump(data, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _summarize_diff(existing: Dict[str, Dict[str, str]], new: Dict[str, Dict[str, str]]) -> Tuple[int, int, int]:
    """Return (added, modified, removed)."""
    existing_keys = set(existing)
    new_keys = set(new)
    added = len(new_keys - existing_keys)
    removed = len(existing_keys - new_keys)
    modified = sum(1 for k in existing_keys & new_keys if existing[k] != new[k])
    return added, modified, removed


def _cmd_verify(
    existing: Dict[str, Dict[str, str]],
    db_snapshot: Dict[str, Dict[str, str]],
) -> int:
    added, modified, removed = _summarize_diff(existing, db_snapshot)
    print(f"existing entries:    {len(existing)}")
    print(f"db entries:          {len(db_snapshot)}")
    print(f"only in db (would-add by extend): {added}")
    print(f"hash-diff (rows present in both): {modified}")
    print(f"only in existing (db missing):    {removed}")
    if modified:
        print("\nFirst 5 diffs:")
        diff_keys = sorted((k for k in set(existing) & set(db_snapshot) if existing[k] != db_snapshot[k]), key=int)[:5]
        for k in diff_keys:
            e, d = existing[k], db_snapshot[k]
            print(f"  block {k}:")
            for field in ("block_hash", "messages_hash", "txlist_hash", "ledger_hash"):
                if e.get(field, "") != d.get(field, ""):
                    print(f"    {field}: existing={e.get(field,'')[:16]}... db={d.get(field,'')[:16]}...")
    return 1 if (modified or removed) else 0


def _cmd_extend(
    existing: Dict[str, Dict[str, str]],
    db_snapshot: Dict[str, Dict[str, str]],
) -> Dict[str, Dict[str, str]]:
    merged = dict(existing)
    added = 0
    for k, v in db_snapshot.items():
        if k not in merged:
            merged[k] = v
            added += 1
    logger.info("extend: added %d new entries; preserved %d existing", added, len(existing))
    return merged


def _cmd_rebuild(db_snapshot: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    logger.info("rebuild: wrote %d entries straight from DB", len(db_snapshot))
    return dict(db_snapshot)


# Write modes that (re)generate the consensus source of truth and therefore
# require explicit source-host confirmation. `verify` is read-only and exempt.
_WRITE_MODES = ("extend", "rebuild")


def _require_confirmed_source(mode: str, db_host: str, confirm_source_host: Optional[str]) -> None:
    """Gate write modes behind an explicit source-host acknowledgment.

    `reference_hashes.json` is the consensus replay baseline; regenerating it
    from an unvalidated DB (e.g. the dev docker MySQL that RDS_* points at in
    the dev tree) could silently bake a wrong baseline. So for `extend`/`rebuild`
    we print the resolved source host prominently and refuse to proceed unless
    the operator passes `--confirm-source-host <host>` matching that host.

    Read-only `verify` is exempt. Raises SystemExit on a missing/mismatched
    confirmation; returns None when the source is confirmed.
    """
    if mode not in _WRITE_MODES:
        return

    banner = "=" * 72
    print(banner, file=sys.stderr)
    print(f"  SOURCE DB host : {db_host}", file=sys.stderr)
    print(f"  mode           : {mode}  (WRITES reference_hashes.json)", file=sys.stderr)
    print("  reference_hashes.json is the CONSENSUS SOURCE OF TRUTH. It must", file=sys.stderr)
    print("  only be generated from a PROD-VALIDATED chain state (prod RDS, or a", file=sys.stderr)
    print("  dev reindex validated against prod with ZERO divergence via", file=sys.stderr)
    print("  compare_tables.py). Confirm this host ONLY if it meets that bar.", file=sys.stderr)
    print(banner, file=sys.stderr)

    if confirm_source_host != db_host:
        raise SystemExit(
            f"::error::refusing to write reference_hashes.json from {db_host} without "
            f"--confirm-source-host {db_host} "
            f"(got --confirm-source-host={confirm_source_host!r}). "
            "Only confirm a host that holds a PROD-validated chain state."
        )
    logger.info("Source host %s confirmed for %s mode.", db_host, mode)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("extend", "rebuild", "verify"), default="extend")
    p.add_argument(
        "--snapshot-path",
        default=str(Path(__file__).resolve().parents[1] / "snapshots" / "reference_hashes.json"),
    )
    p.add_argument(
        "--check-py-path",
        default=str(Path(__file__).resolve().parents[1] / "src" / "index_core" / "check.py"),
    )
    p.add_argument("--db-host", default=os.environ.get("RDS_HOSTNAME"))
    p.add_argument("--db-user", default=os.environ.get("RDS_USER"))
    p.add_argument("--db-password", default=os.environ.get("RDS_PASSWORD"))
    p.add_argument("--db-name", default=os.environ.get("RDS_DATABASE", "btc_stamps"))
    p.add_argument(
        "--confirm-source-host",
        default=None,
        help=(
            "Required for --mode extend/rebuild: must equal the resolved source DB "
            "host. Acknowledges that this host holds a PROD-validated chain state "
            "(reference_hashes.json is the consensus source of truth)."
        ),
    )
    p.add_argument("--start-block", type=int, default=779652, help="lowest block_index to fetch from DB")
    p.add_argument("--end-block", type=int, default=None, help="highest block_index to fetch (default: tip)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    if not (args.db_host and args.db_user and args.db_password):
        print("::error::DB credentials not configured. Set RDS_HOSTNAME/RDS_USER/RDS_PASSWORD or pass --db-*", file=sys.stderr)
        return 2

    # Source-of-truth guard: fast-fail BEFORE touching the DB if a write mode
    # hasn't explicitly confirmed the resolved source host.
    _require_confirmed_source(args.mode, args.db_host, args.confirm_source_host)

    snapshot_path = Path(args.snapshot_path)
    check_py_path = Path(args.check_py_path)

    # Fetch BEFORE mutating disk — fast-fail if DB is unreachable.
    logger.info("Connecting to %s as %s, db=%s ...", args.db_host, args.db_user, args.db_name)
    conn = _connect_db(args.db_host, args.db_user, args.db_password, args.db_name)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MIN(block_index), MAX(block_index), COUNT(*) FROM blocks")
            min_b, max_b, count = cur.fetchone()
        logger.info("DB has %d blocks, range %s..%s", count, min_b, max_b)

        db_snapshot = _fetch_db_blocks(conn, args.start_block, args.end_block)
        logger.info("Fetched %d entries from DB (start_block=%d)", len(db_snapshot), args.start_block)
    finally:
        conn.close()

    existing, existing_meta = _load_existing(snapshot_path)
    logger.info("Loaded %d existing entries from %s", len(existing), snapshot_path)

    if args.mode == "verify":
        return _cmd_verify(existing, db_snapshot)

    if args.mode == "extend":
        merged = _cmd_extend(existing, db_snapshot)
    elif args.mode == "rebuild":
        merged = _cmd_rebuild(db_snapshot)
    else:
        raise SystemExit(f"unknown mode {args.mode!r}")

    added, modified, removed = _summarize_diff(existing, merged)
    print(f"diff summary: +{added} added, ~{modified} modified, -{removed} removed")

    # Last line of defense — checkpoint validation before writing.
    checkpoints = _read_checkpoints_from_source(check_py_path)
    _validate_against_checkpoints(merged, checkpoints)

    _atomic_write(snapshot_path, _wrap_for_writing(merged, existing_meta))
    logger.info("Wrote %d entries to %s", len(merged), snapshot_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
