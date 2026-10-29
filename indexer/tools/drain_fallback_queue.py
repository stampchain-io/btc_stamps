#!/usr/bin/env python3
"""Inspect and drain the Counterparty fallback reprocessing queue (issue #957).

The indexer records every block it processed without Counterparty data in a
SQLite file (``fallback_sessions`` + ``failed_blocks``). Normally the recovery
rollback closes the session once CP is back. When that did not happen the file
keeps an open session that the indexer will act on at its next start, and the
pre-#957 writer left millions of orphaned rows behind (1 GB in production).

Run this with the indexer STOPPED; it opens the same file.

    poetry run python tools/drain_fallback_queue.py --status
    poetry run python tools/drain_fallback_queue.py --purge-orphans --vacuum
    poetry run python tools/drain_fallback_queue.py --close-session 969004 --reindexed-from 969004

``--close-session`` refuses unless ``--reindexed-from N`` covers the whole session
(N <= session start), because closing a session tells the indexer those blocks
have CP data. ``--force`` overrides that after printing the uncovered range; use it
only when the uncovered blocks were verified by other means.

This tool never touches the MySQL indexer database.
"""

import argparse
import os
import sqlite3
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from index_core.reprocess_safety import MAX_ROLLBACK_BLOCKS, get_safe_reprocess_db_path  # noqa: E402


def open_queue(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def inspect(conn: sqlite3.Connection, indexer_height: Optional[int] = None) -> Dict[str, Any]:
    """Read-only summary of the queue file."""
    if not _table_exists(conn, "fallback_sessions"):
        return {"sessions": [], "orphan_rows": 0, "tx_queue_rows": 0, "initialized": False}

    sessions: List[Dict[str, Any]] = []
    rows = conn.execute("""
        SELECT s.id, s.start_block_index, s.created_at, s.updated_at,
               COUNT(f.id), MIN(f.block_index), MAX(f.block_index)
        FROM fallback_sessions s
        LEFT JOIN failed_blocks f ON f.session_id = s.id
        GROUP BY s.id
        ORDER BY s.start_block_index
        """).fetchall()
    for session_id, start, created_at, updated_at, count, first, last in rows:
        entry: Dict[str, Any] = {
            "session_id": session_id,
            "start_block_index": start,
            "created_at": created_at,
            "updated_at": updated_at,
            "block_count": count,
            "first_block": first,
            "last_block": last,
            "blocks_behind_indexer": None,
            "recoverable_by_rollback": None,
        }
        if indexer_height is not None:
            behind = indexer_height - start
            entry["blocks_behind_indexer"] = behind
            entry["recoverable_by_rollback"] = behind <= MAX_ROLLBACK_BLOCKS
        sessions.append(entry)

    orphan_rows = conn.execute(
        "SELECT COUNT(*) FROM failed_blocks WHERE session_id NOT IN (SELECT id FROM fallback_sessions)"
    ).fetchone()[0]
    tx_queue_rows = (
        conn.execute("SELECT COUNT(*) FROM reprocess_queue").fetchone()[0] if _table_exists(conn, "reprocess_queue") else 0
    )
    return {"sessions": sessions, "orphan_rows": orphan_rows, "tx_queue_rows": tx_queue_rows, "initialized": True}


def purge_orphans(conn: sqlite3.Connection) -> int:
    """Delete failed_blocks rows whose session is gone. Lossless: nothing reads them."""
    cur = conn.execute("DELETE FROM failed_blocks WHERE session_id NOT IN (SELECT id FROM fallback_sessions)")
    conn.commit()
    return cur.rowcount


def close_session(
    conn: sqlite3.Connection, start_block: int, reindexed_from: Optional[int], force: bool = False
) -> Dict[str, Any]:
    """Close one session, returning what was removed and what (if anything) was not covered.

    Raises ValueError when the session does not exist or when ``reindexed_from`` does
    not cover it and ``force`` is False.
    """
    row = conn.execute("SELECT id FROM fallback_sessions WHERE start_block_index = ?", (start_block,)).fetchone()
    if row is None:
        raise ValueError(f"No fallback session starts at block {start_block}")
    session_id = row[0]
    blocks = [
        r[0]
        for r in conn.execute("SELECT block_index FROM failed_blocks WHERE session_id = ? ORDER BY block_index", (session_id,))
    ]

    covered_from = reindexed_from if reindexed_from is not None else None
    uncovered = [b for b in blocks if covered_from is None or b < covered_from]
    if uncovered and not force:
        raise ValueError(
            f"Reindex from {reindexed_from} does not cover {len(uncovered)} session block(s) "
            f"({uncovered[0]}-{uncovered[-1]}). Reindex from {start_block} or earlier, or pass --force after "
            f"verifying those blocks by other means."
        )

    conn.execute("DELETE FROM failed_blocks WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM fallback_sessions WHERE id = ?", (session_id,))
    conn.commit()
    return {"start_block_index": start_block, "removed_blocks": len(blocks), "uncovered_blocks": uncovered, "forced": force}


def vacuum(conn: sqlite3.Connection) -> None:
    conn.execute("VACUUM")


def _print_status(db_path: str, summary: Dict[str, Any]) -> None:
    size_mb = os.path.getsize(db_path) / (1024 * 1024) if os.path.exists(db_path) else 0.0
    print(f"Queue file: {db_path} ({size_mb:.1f} MB)")
    if not summary["initialized"]:
        print("No fallback tables in this file (never used for fallback).")
        return
    if not summary["sessions"]:
        print("Open fallback sessions: none")
    for s in summary["sessions"]:
        verdict = ""
        if s["recoverable_by_rollback"] is True:
            verdict = f" | recoverable by rollback ({s['blocks_behind_indexer']} blocks behind indexer)"
        elif s["recoverable_by_rollback"] is False:
            verdict = (
                f" | NOT recoverable: {s['blocks_behind_indexer']} blocks behind indexer, bound is {MAX_ROLLBACK_BLOCKS}. "
                f"The indexer will refuse to start until this session is closed."
            )
        print(
            f"Session {s['session_id']}: start={s['start_block_index']} blocks={s['block_count']} "
            f"range={s['first_block']}-{s['last_block']} created={s['created_at']} updated={s['updated_at']}{verdict}"
        )
    print(f"Orphaned failed_blocks rows: {summary['orphan_rows']}")
    print(f"Per-transaction reprocess_queue rows: {summary['tx_queue_rows']} (this table has no producer; 0 is normal)")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-path", help="Queue file (default: the indexer's production/dev path)")
    parser.add_argument("--status", action="store_true", help="Print sessions, orphan rows and file size (read-only)")
    parser.add_argument("--indexer-height", type=int, help="Indexer's last block, used to judge rollback recoverability")
    parser.add_argument("--purge-orphans", action="store_true", help="Delete failed_blocks rows without a session")
    parser.add_argument("--close-session", type=int, metavar="START", help="Close the session that starts at START")
    parser.add_argument(
        "--reindexed-from", type=int, metavar="N", help="Block the indexer was reindexed from (must be <= START)"
    )
    parser.add_argument("--force", action="store_true", help="Close even when --reindexed-from does not cover the session")
    parser.add_argument("--vacuum", action="store_true", help="VACUUM the file after changes to reclaim space")
    args = parser.parse_args(argv)

    db_path = args.db_path or get_safe_reprocess_db_path()
    if not os.path.exists(db_path):
        print(f"Queue file not found: {db_path}")
        return 1

    wal = db_path + "-wal"
    if os.path.exists(wal) and os.path.getsize(wal) > 0 and (args.purge_orphans or args.close_session or args.vacuum):
        print(f"Warning: {wal} is non-empty; make sure the indexer is stopped before modifying the queue.")

    conn = open_queue(db_path)
    try:
        if args.status or not (args.purge_orphans or args.close_session or args.vacuum):
            _print_status(db_path, inspect(conn, args.indexer_height))

        if args.purge_orphans:
            deleted = purge_orphans(conn)
            print(f"Purged {deleted} orphaned failed_blocks rows")

        if args.close_session is not None:
            try:
                result = close_session(conn, args.close_session, args.reindexed_from, force=args.force)
            except ValueError as e:
                print(f"Refused: {e}")
                return 2
            note = ""
            if result["uncovered_blocks"]:
                u = result["uncovered_blocks"]
                note = f" (forced: {len(u)} blocks {u[0]}-{u[-1]} were not covered by the reindex)"
            print(
                f"Closed fallback session from block {result['start_block_index']}: {result['removed_blocks']} blocks removed{note}"
            )

        if args.vacuum:
            before = os.path.getsize(db_path)
            vacuum(conn)
            after = os.path.getsize(db_path)
            print(f"VACUUM done: {before / (1024 * 1024):.1f} MB -> {after / (1024 * 1024):.1f} MB")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
