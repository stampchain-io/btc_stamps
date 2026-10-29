"""Tests for tools/drain_fallback_queue.py (issue #957 operator tool)."""

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from src.index_core.reprocess_safety import MAX_ROLLBACK_BLOCKS
from src.index_core.reprocessing_queue import ReprocessingQueue

START = 969004
TOOL_PATH = Path(__file__).resolve().parents[1] / "tools" / "drain_fallback_queue.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("drain_fallback_queue", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def queue_db(tmp_path):
    """A queue file with one session of 10 blocks and 25 orphan rows, indexer closed."""
    if ReprocessingQueue._instance is not None:
        try:
            ReprocessingQueue._instance.close()
        except Exception:
            pass
    ReprocessingQueue._instance = None
    db_path = str(tmp_path / "reprocess_queue.db")
    queue = ReprocessingQueue(db_path=db_path)
    for block in range(START, START + 10):
        queue.add_failed_block(START, block)
    queue.close()
    ReprocessingQueue._instance = None

    conn = sqlite3.connect(db_path)
    for stale_id in range(100, 105):
        for block in range(START, START + 5):
            conn.execute("INSERT INTO failed_blocks (session_id, block_index) VALUES (?, ?)", (stale_id, block))
    conn.commit()
    conn.close()
    return db_path


def test_inspect_reports_sessions_and_orphans(tool, queue_db):
    conn = tool.open_queue(queue_db)
    summary = tool.inspect(conn, indexer_height=START + 9)
    conn.close()
    assert summary["initialized"] is True
    assert summary["orphan_rows"] == 25
    assert summary["tx_queue_rows"] == 0
    (session,) = summary["sessions"]
    assert session["start_block_index"] == START
    assert session["block_count"] == 10
    assert (session["first_block"], session["last_block"]) == (START, START + 9)
    assert session["recoverable_by_rollback"] is True


def test_inspect_flags_unrecoverable_session(tool, queue_db):
    conn = tool.open_queue(queue_db)
    summary = tool.inspect(conn, indexer_height=START + MAX_ROLLBACK_BLOCKS + 1)
    conn.close()
    assert summary["sessions"][0]["recoverable_by_rollback"] is False


def test_inspect_without_height_has_no_verdict(tool, queue_db):
    conn = tool.open_queue(queue_db)
    summary = tool.inspect(conn)
    conn.close()
    assert summary["sessions"][0]["recoverable_by_rollback"] is None


def test_purge_orphans_keeps_live_session_rows(tool, queue_db):
    conn = tool.open_queue(queue_db)
    assert tool.purge_orphans(conn) == 25
    assert conn.execute("SELECT COUNT(*) FROM failed_blocks").fetchone()[0] == 10
    assert tool.purge_orphans(conn) == 0
    conn.close()


def test_close_session_refuses_partial_reindex(tool, queue_db):
    conn = tool.open_queue(queue_db)
    with pytest.raises(ValueError, match="does not cover 3 session block"):
        tool.close_session(conn, START, reindexed_from=START + 3)
    with pytest.raises(ValueError, match="does not cover 10 session block"):
        tool.close_session(conn, START, reindexed_from=None)
    assert conn.execute("SELECT COUNT(*) FROM fallback_sessions").fetchone()[0] == 1
    conn.close()


def test_close_session_with_full_reindex(tool, queue_db):
    conn = tool.open_queue(queue_db)
    result = tool.close_session(conn, START, reindexed_from=START)
    assert result == {"start_block_index": START, "removed_blocks": 10, "uncovered_blocks": [], "forced": False}
    assert conn.execute("SELECT COUNT(*) FROM fallback_sessions").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM failed_blocks WHERE session_id NOT IN (100,101,102,103,104)").fetchone()[0] == 0
    conn.close()


def test_close_session_force_lists_uncovered_blocks(tool, queue_db):
    conn = tool.open_queue(queue_db)
    result = tool.close_session(conn, START, reindexed_from=START + 3, force=True)
    assert result["forced"] is True
    assert result["uncovered_blocks"] == [START, START + 1, START + 2]
    assert conn.execute("SELECT COUNT(*) FROM fallback_sessions").fetchone()[0] == 0
    conn.close()


def test_close_unknown_session_raises(tool, queue_db):
    conn = tool.open_queue(queue_db)
    with pytest.raises(ValueError, match="No fallback session starts at block"):
        tool.close_session(conn, START + 1, reindexed_from=START)
    conn.close()


def test_main_status_is_read_only(tool, queue_db, capsys):
    assert tool.main(["--db-path", queue_db, "--status", "--indexer-height", str(START + 9)]) == 0
    out = capsys.readouterr().out
    assert f"start={START} blocks=10" in out
    assert "Orphaned failed_blocks rows: 25" in out
    assert "recoverable by rollback" in out
    conn = sqlite3.connect(queue_db)
    assert conn.execute("SELECT COUNT(*) FROM failed_blocks").fetchone()[0] == 35
    conn.close()


def test_main_refused_close_returns_2(tool, queue_db, capsys):
    assert tool.main(["--db-path", queue_db, "--close-session", str(START), "--reindexed-from", str(START + 5)]) == 2
    assert "Refused" in capsys.readouterr().out


def test_main_purge_close_vacuum(tool, queue_db, capsys):
    rc = tool.main(
        ["--db-path", queue_db, "--purge-orphans", "--close-session", str(START), "--reindexed-from", str(START), "--vacuum"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Purged 25 orphaned" in out
    assert f"Closed fallback session from block {START}: 10 blocks removed" in out
    assert "VACUUM done" in out
    conn = sqlite3.connect(queue_db)
    assert conn.execute("SELECT COUNT(*) FROM failed_blocks").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM fallback_sessions").fetchone()[0] == 0
    conn.close()


def test_main_missing_file(tool, tmp_path):
    assert tool.main(["--db-path", str(tmp_path / "nope.db"), "--status"]) == 1
