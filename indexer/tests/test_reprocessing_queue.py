import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.index_core import config  # For REPROCESS_MAX_ATTEMPTS etc.
from src.index_core.reprocessing_queue import ReprocessingQueue, exponential_backoff


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton instance before and after each test"""
    ReprocessingQueue._instance = None
    yield
    if ReprocessingQueue._instance is not None:
        ReprocessingQueue._instance.close()
    ReprocessingQueue._instance = None


@pytest.fixture
def queue(tmp_path: Path):
    """Create a real in-memory queue instance for testing"""
    q = ReprocessingQueue(db_path=":memory:")
    yield q
    q.close()


@pytest.mark.parametrize("attempt, expected_delay", [(0, 1), (1, 2), (2, 4), (3, 8), (5, 32), (6, 60)])
def test_exponential_backoff(attempt: int, expected_delay: float):
    with patch("src.index_core.reprocessing_queue.random.uniform", return_value=0):
        assert exponential_backoff(attempt) == expected_delay


def test_enqueue_dequeue(queue):
    # Manually insert with past next_retry_time to ensure it's ready for dequeue
    with queue.lock:
        queue.conn.execute(
            """
            INSERT INTO reprocess_queue
            (tx_hash, attempts, next_retry_time, status, added_at)
            VALUES (?, 0, 0, 'pending', unixepoch())
            """,
            ("tx1",),
        )
        queue.conn.commit()

    items = queue.dequeue(1)
    assert len(items) == 1
    assert items[0][0] == "tx1"
    assert items[0][1] == 0  # attempts


def test_update_success(queue):
    queue.enqueue("tx1")
    queue.dequeue(1)
    queue.update_status("tx1", success=True)
    status = queue.get_status()
    assert status.get("done", 0) == 1
    assert status.get("pending", 0) == 0


def test_update_failure_retry(queue, monkeypatch):
    monkeypatch.setattr("time.time", lambda: 0)  # Freeze time
    # Patch random.uniform to return 0 for deterministic backoff
    monkeypatch.setattr("src.index_core.reprocessing_queue.random.uniform", lambda a, b: 0)

    queue.enqueue("tx1")
    queue.dequeue(1)
    queue.update_status("tx1", success=False)
    # Check attempts increased, status failed, next_retry set
    with queue.lock:
        cur = queue.conn.cursor()
        cur.execute('SELECT attempts, status, next_retry_time FROM reprocess_queue WHERE tx_hash = "tx1"')
        row = cur.fetchone()
        assert row[0] == 1
        assert row[1] == "failed"
        # With time=0 and exponential_backoff(1)=2 (no jitter), next_retry_time should be 2
        assert row[2] == 2.0


def test_max_attempts(queue):
    max_attempts = getattr(config, "REPROCESS_MAX_ATTEMPTS", 5)

    # Insert with past next_retry_time
    with queue.lock:
        queue.conn.execute(
            """
            INSERT INTO reprocess_queue
            (tx_hash, attempts, next_retry_time, status, added_at)
            VALUES (?, 0, 0, 'pending', unixepoch())
            """,
            ("tx1",),
        )
        queue.conn.commit()

    # Simulate max_attempts failures
    for i in range(max_attempts):
        items = queue.dequeue(1)
        if items:
            queue.update_status("tx1", success=False)
            # After failure, manually update next_retry_time to 0 to make it ready for next dequeue
            if i < max_attempts - 1:
                with queue.lock:
                    queue.conn.execute("UPDATE reprocess_queue SET next_retry_time = 0 WHERE tx_hash = ?", ("tx1",))
                    queue.conn.commit()

    # Check the final state - with the fix, attempts should equal max_attempts
    with queue.lock:
        cur = queue.conn.cursor()
        cur.execute("SELECT attempts, status FROM reprocess_queue WHERE tx_hash = ?", ("tx1",))
        row = cur.fetchone()
        assert row[0] == max_attempts  # Should be 5 if max_attempts is 5
        assert row[1] == "failed"

    status = queue.get_status()
    assert status.get("failed", 0) == 1
    assert status["maxed_attempts"] == 1  # Now this should be 1


def test_cleanup(queue, monkeypatch):
    # Set initial time for enqueue
    initial_time = time.time()
    monkeypatch.setattr("time.time", lambda: initial_time)

    queue.enqueue("tx1")
    queue.dequeue(1)
    queue.update_status("tx1", success=True)

    # Now advance time to beyond cleanup threshold (86400 seconds)
    future_time = initial_time + 100000  # Well beyond the 86400 threshold
    monkeypatch.setattr("time.time", lambda: future_time)

    # Need to manually update the added_at timestamp to be old enough
    with queue.lock:
        cur = queue.conn.cursor()
        old_timestamp = future_time - 90000  # Make it old enough to be cleaned
        cur.execute('UPDATE reprocess_queue SET added_at = ? WHERE tx_hash = "tx1"', (old_timestamp,))
        queue.conn.commit()

    deleted = queue.cleanup()
    assert deleted == 1

    status = queue.get_status()
    # After cleanup, should have no items
    assert status.get("done", 0) == 0
    assert status.get("maxed_attempts", 0) == 0


def test_concurrency(queue):
    import threading

    # First enqueue all items with past next_retry_time
    with queue.lock:
        for i in range(5):
            queue.conn.execute(
                """
                INSERT INTO reprocess_queue
                (tx_hash, attempts, next_retry_time, status, added_at)
                VALUES (?, 0, 0, 'pending', unixepoch())
                """,
                (f"tx{i}",),
            )
        queue.conn.commit()

    # Now process them concurrently
    def worker(q):
        items = q.dequeue(1)
        if items:
            tx_hash = items[0][0]
            q.update_status(tx_hash, success=True)

    threads = [threading.Thread(target=worker, args=(queue,)) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    status = queue.get_status()
    assert status.get("done", 0) == 5


# Add more: error handling, status checks, etc.
def test_get_status_empty(queue):
    status = queue.get_status()
    assert status.get("maxed_attempts", 0) == 0
    # Empty queue should have no items in any status
    for key in ["pending", "processing", "done", "failed"]:
        assert status.get(key, 0) == 0


def test_clear_all_fallbacks(queue):
    # First add some fallback state - use correct Dict[int, bool] format
    queue.save_fallback_state(100, {123: True})

    # Verify it was saved
    state = queue.load_fallback_state(100)
    assert state == {123: True}

    # Clear all fallbacks
    queue.clear_all_fallbacks()

    # Verify it was cleared
    state = queue.load_fallback_state(100)
    assert state is None
