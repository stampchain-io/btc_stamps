"""Tests for the startup chain-integrity check (issue #779).

The function under test is ``index_core.blocks.verify_recent_chain_integrity``.
It reads the last N stored blocks from the DB and compares each ``block_hash``
against ``backend_instance.getblockhash(block_index)``. The OLDEST diverging
block is returned (so the caller can roll back from divergence-1 and re-process
everything after); ``None`` means clean / inconclusive.
"""

import os
from unittest.mock import MagicMock, patch

os.environ["TESTING"] = "1"
os.environ["USE_TEST_DB"] = "1"
os.environ["MOCK_DB"] = "1"
os.environ["RPC_USER"] = "rpc"
os.environ["RPC_PASSWORD"] = "rpc"
os.environ["RPC_IP"] = "127.0.0.1"
os.environ["RPC_PORT"] = "8332"


def _make_db(rows):
    """Return a mock pymysql connection whose cursor.fetchall() yields ``rows``.

    Rows are returned in the DESC order the SQL query uses.
    """
    db = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = list(rows)
    db.cursor.return_value.__enter__.return_value = cursor
    db.cursor.return_value.__exit__.return_value = None
    return db


def test_clean_chain_returns_none():
    """Every stored block matches bitcoind → return None."""
    from index_core.blocks import verify_recent_chain_integrity

    rows = [(102, "hash102"), (101, "hash101"), (100, "hash100")]  # DESC
    db = _make_db(rows)

    with patch("index_core.blocks.backend_instance") as backend:
        backend.getblockhash.side_effect = lambda i: f"hash{i}"
        assert verify_recent_chain_integrity(db, depth=3) is None

    # All three blocks were checked, in ascending order.
    assert [call.args[0] for call in backend.getblockhash.call_args_list] == [100, 101, 102]


def test_oldest_divergence_is_returned():
    """When blocks 100..102 all diverge, the OLDEST (100) must be returned.

    Rolling back to divergence-1 from the newest mismatch would miss the
    older stale rows; rolling back to divergence-1 from the oldest catches
    everything.
    """
    from index_core.blocks import verify_recent_chain_integrity

    rows = [(102, "stale102"), (101, "stale101"), (100, "stale100")]
    db = _make_db(rows)

    with patch("index_core.blocks.backend_instance") as backend:
        backend.getblockhash.side_effect = lambda i: f"canonical{i}"
        assert verify_recent_chain_integrity(db, depth=3) == 100

    # We stop on the first mismatch — only one canonical lookup happens.
    assert backend.getblockhash.call_count == 1


def test_single_block_diverges_in_middle():
    """Mid-window divergence: 100 matches, 101 diverges, 102 doesn't matter."""
    from index_core.blocks import verify_recent_chain_integrity

    rows = [(102, "hash102"), (101, "stale101"), (100, "hash100")]
    db = _make_db(rows)

    with patch("index_core.blocks.backend_instance") as backend:
        backend.getblockhash.side_effect = lambda i: f"hash{i}"
        assert verify_recent_chain_integrity(db, depth=3) == 101

    # 100 (ok) then 101 (diverges, stop).
    assert backend.getblockhash.call_count == 2


def test_depth_zero_is_no_op():
    """depth=0 disables the check entirely — no DB or backend calls."""
    from index_core.blocks import verify_recent_chain_integrity

    db = MagicMock()
    with patch("index_core.blocks.backend_instance") as backend:
        assert verify_recent_chain_integrity(db, depth=0) is None
    assert not db.cursor.called
    assert not backend.getblockhash.called


def test_empty_blocks_table_returns_none():
    """Fresh DB with no stored blocks → None, never calls backend."""
    from index_core.blocks import verify_recent_chain_integrity

    db = _make_db([])
    with patch("index_core.blocks.backend_instance") as backend:
        assert verify_recent_chain_integrity(db, depth=10) is None
    assert not backend.getblockhash.called


def test_db_read_failure_returns_none_safely():
    """A DB read error must not raise — startup should not be blocked."""
    from index_core.blocks import verify_recent_chain_integrity

    db = MagicMock()
    db.cursor.side_effect = RuntimeError("DB went away")
    with patch("index_core.blocks.backend_instance") as backend:
        assert verify_recent_chain_integrity(db, depth=10) is None
    assert not backend.getblockhash.called


def test_backend_failure_returns_best_effort():
    """If bitcoind getblockhash fails mid-check, return any divergence found
    so far (None if none yet). Never raises."""
    from index_core.blocks import verify_recent_chain_integrity

    rows = [(102, "hash102"), (101, "hash101"), (100, "hash100")]
    db = _make_db(rows)

    with patch("index_core.blocks.backend_instance") as backend:
        # 100 ok, then 101 raises → result is None (no divergence found yet)
        def fake_getblockhash(i):
            if i == 100:
                return "hash100"
            raise ConnectionError("bitcoind unreachable")

        backend.getblockhash.side_effect = fake_getblockhash
        assert verify_recent_chain_integrity(db, depth=3) is None


def test_945189_scenario():
    """Regression: the original 945,189 stale-row incident. The stored
    block_hash for one historical block diverges from bitcoind; the check
    must surface it so the caller rolls back to 945,188 and reprocesses
    945,189 onward."""
    from index_core.blocks import verify_recent_chain_integrity

    # Tip is 945,288. Stored 945,189 is the orphaned hash; everything else
    # matches. depth=100 covers the affected window.
    canonical = {i: f"hash{i}" for i in range(945_188, 945_289)}
    rows = []
    for i in range(945_288, 945_188, -1):  # DESC
        stored = canonical[i] if i != 945_189 else "orphaned_945189_hash"
        rows.append((i, stored))
    db = _make_db(rows)

    with patch("index_core.blocks.backend_instance") as backend:
        backend.getblockhash.side_effect = lambda i: canonical[i]
        assert verify_recent_chain_integrity(db, depth=100) == 945_189
