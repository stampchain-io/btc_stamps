"""
Regression tests for issue #957: Counterparty fallback mode skipped valid stamps.

Production entered CP fallback mode when CP was healthy but had not parsed the tip
block within the readiness wait, then processed every later block without CP data.
The rollback that should redo those blocks never fired (a recovery flag latched after
the first successful recovery) and could not succeed once the session outgrew the
rollback safety bound. The reprocessing queue also re-inserted every block of the
session on every new block.

These tests cover:
- the tip race: CP reachable but behind must wait, never fall back, and the stamp
  issuance must reach the processor once CP catches up;
- fallback still works for a genuine outage, bounded so it stays recoverable;
- recovery requests a rollback on every session, not only the first;
- the recovery rollback drains the session, measured against indexed state;
- reprocessing-queue writes are deduplicated and orphans are purged.
"""

import sqlite3
import threading
import time
from unittest.mock import patch

import pytest

from src.index_core.pipeline_utils import CPBlocksPipeline
from src.index_core.reprocessing_queue import ReprocessingQueue

TIP = 973464
ISSUANCE = {
    "tx_hash": "7046278a4bda05c7dd3063dd10607800cbb92ba6f8c7c41f49bd985edee6bbed",
    "asset": "A1301847304853164300",
    "description": "stamp:",
}
HEALTHY = [{"name": "local", "url": "http://127.0.0.1:4000"}]


def _global_fallback_enabled():
    from index_core.fetch_utils import is_global_fallback_enabled

    return is_global_fallback_enabled()


@pytest.fixture(autouse=True)
def isolated_queue(tmp_path):
    """Give every test its own on-disk reprocessing queue and a clean global flag."""
    from index_core.fetch_utils import set_global_fallback_mode

    if ReprocessingQueue._instance is not None:
        try:
            ReprocessingQueue._instance.close()
        except Exception:
            pass
    ReprocessingQueue._instance = None
    db_path = str(tmp_path / "reprocess_queue.db")
    ReprocessingQueue._instance = ReprocessingQueue(db_path=db_path)
    set_global_fallback_mode(False)
    yield db_path
    set_global_fallback_mode(False)
    if ReprocessingQueue._instance is not None:
        ReprocessingQueue._instance.close()
    ReprocessingQueue._instance = None


@pytest.fixture
def near_tip_backend():
    """Bitcoin tip == the block being indexed, for both backend references."""
    with patch("src.index_core.pipeline_utils.backend_instance") as pipe_backend, patch(
        "src.index_core.blocks.backend_instance"
    ) as blocks_backend:
        for backend in (pipe_backend, blocks_backend):
            backend.getblockcount.return_value = TIP
            backend.invalidate_blockcount_cache.return_value = None
        yield pipe_backend


@pytest.fixture
def node_health():
    """Control CP node health as seen by the pipeline."""
    with patch("src.index_core.pipeline_utils.update_healthy_nodes") as update, patch(
        "src.index_core.pipeline_utils.get_healthy_nodes"
    ) as get:
        update.return_value = None
        get.return_value = HEALTHY
        yield get


def _wait_until(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _run_worker(pipeline, start_block):
    pipeline.current_block = start_block
    pipeline.running = True
    pipeline.shutdown_flag.clear()
    thread = threading.Thread(target=pipeline._fetch_blocks_worker, daemon=True)
    thread.start()
    return thread


def _stop_worker(pipeline, thread):
    pipeline.running = False
    pipeline.shutdown_flag.set()
    thread.join(timeout=10)
    pipeline.fetch_executor.shutdown(wait=False)


class TestTipRace:
    def test_cp_behind_tip_waits_and_stamp_is_not_skipped(self, near_tip_backend, node_health):
        """CP healthy but not yet at the block: the worker waits, then serves the issuance."""
        cp_height = {"value": TIP - 1}
        readiness_checks = {"count": 0}

        def cp_ready(block_index, max_wait=0, check_interval=0):
            readiness_checks["count"] += 1
            return cp_height["value"] >= block_index

        def cp_fetch(start, end, **_kwargs):
            return {
                b: {"block_index": b, "issuances": [ISSUANCE] if b == TIP else []}
                for b in range(start, end + 1)
                if b <= cp_height["value"]
            }

        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, initial_fetch_size=1, fallback_mode=True)
        pipeline.fetch_interval = 0.01
        with patch("src.index_core.pipeline_utils.wait_for_cp_block_processed", side_effect=cp_ready), patch(
            "src.index_core.pipeline_utils.fetch_cp_blocks_skipping_empty", side_effect=cp_fetch
        ):
            thread = _run_worker(pipeline, TIP)
            try:
                # Several readiness timeouts happen while CP is one block behind.
                assert _wait_until(lambda: readiness_checks["count"] >= 3)
                assert pipeline.fallback_started_at is None
                assert not _global_fallback_enabled()
                assert pipeline.get_block(TIP) is None, "no fallback block may stand in for an unparsed block"
                assert pipeline.failed_cp_blocks == set()

                # CP parses the tip block.
                cp_height["value"] = TIP
                assert _wait_until(lambda: pipeline.get_block(TIP) is not None)
                block = pipeline.get_block(TIP)
                assert not block.get("fallback_mode")
                assert block["issuances"] == [ISSUANCE]
            finally:
                _stop_worker(pipeline, thread)

        stats = ReprocessingQueue.get_instance().get_fallback_stats()
        assert stats["session_count"] == 0
        assert stats["total_failed_blocks"] == 0

    def test_enter_fallback_refused_while_cp_reachable(self, near_tip_backend, node_health):
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        pipeline.current_block = TIP
        pipeline._enter_fallback_mode()
        assert pipeline.fallback_started_at is None
        assert not _global_fallback_enabled()
        assert pipeline.queue == {}

    def test_reachability_check_error_does_not_enter_fallback(self, near_tip_backend):
        with patch("src.index_core.pipeline_utils.update_healthy_nodes", side_effect=RuntimeError("boom")), patch(
            "src.index_core.pipeline_utils.get_healthy_nodes", return_value=[]
        ):
            pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
            pipeline.current_block = TIP
            pipeline._enter_fallback_mode()
        assert pipeline.fallback_started_at is None

    def test_repeated_fetch_failures_with_cp_reachable_do_not_queue_fallback_blocks(self, near_tip_backend, node_health):
        """The failure-threshold path must not create a fallback block when entry is refused."""
        from concurrent.futures import Future

        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        pipeline.current_block = TIP
        for _ in range(pipeline.fallback_failure_threshold):
            future = Future()
            future.set_result({TIP: {"error": "not parsed yet"}})
            with pipeline.fetch_futures_lock:
                pipeline.fetch_futures[TIP] = future
            pipeline._process_completed_futures()
        assert pipeline.fallback_started_at is None
        assert TIP not in pipeline.queue

    def test_global_flag_not_left_on_when_entry_refused_far_from_tip(self, node_health):
        node_health.return_value = []  # genuine outage, but far from the tip
        with patch("src.index_core.blocks.backend_instance") as backend:
            backend.getblockcount.return_value = TIP + 5000
            pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
            pipeline.current_block = TIP
            pipeline._enter_fallback_mode()
        assert pipeline.fallback_started_at is None
        assert not _global_fallback_enabled()


class TestGenuineOutage:
    def test_outage_still_enters_fallback(self, near_tip_backend, node_health):
        node_health.return_value = []
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        pipeline.current_block = TIP
        pipeline._enter_fallback_mode()
        assert pipeline.fallback_started_at == TIP
        assert _global_fallback_enabled()
        block = pipeline.get_block(TIP)
        assert block["fallback_mode"] is True
        assert TIP in pipeline.failed_cp_blocks

    def test_session_is_capped_so_it_stays_recoverable(self, near_tip_backend, node_health, monkeypatch):
        monkeypatch.setenv("CP_FALLBACK_MAX_SESSION_BLOCKS", "3")
        node_health.return_value = []
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        pipeline.current_block = TIP
        pipeline._enter_fallback_mode()
        pipeline.queue.clear()

        for block_index in range(TIP, TIP + 3):
            assert pipeline.get_block(block_index) is not None
            pipeline.confirm_block_processed(block_index)
        assert pipeline.is_fallback_session_full(TIP + 3)
        assert pipeline.get_block(TIP + 3) is None
        assert pipeline.failed_cp_blocks == {TIP, TIP + 1, TIP + 2}

    def test_cap_never_exceeds_rollback_safety_bound(self, monkeypatch):
        from index_core.reprocess_safety import MAX_ROLLBACK_BLOCKS

        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        monkeypatch.setenv("CP_FALLBACK_MAX_SESSION_BLOCKS", str(MAX_ROLLBACK_BLOCKS * 10))
        assert pipeline._max_fallback_session_blocks() == MAX_ROLLBACK_BLOCKS
        monkeypatch.delenv("CP_FALLBACK_MAX_SESSION_BLOCKS")
        assert pipeline._max_fallback_session_blocks() < MAX_ROLLBACK_BLOCKS


class TestRecoveryAndDrain:
    def test_second_session_requests_rollback_after_an_earlier_recovery(self, near_tip_backend, node_health):
        """cp_nodes_healthy_again stays True after recovery; it must not block later sessions."""
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        pipeline.cp_nodes_healthy_again = True  # state left by a completed earlier recovery

        node_health.return_value = []
        pipeline.current_block = TIP
        pipeline._enter_fallback_mode()
        pipeline.get_block(TIP)
        assert pipeline.fallback_started_at == TIP

        node_health.return_value = HEALTHY
        pipeline.last_health_check = 0
        assert pipeline.check_cp_node_recovery() is True
        assert pipeline.rollback_requested is True
        assert pipeline.rollback_target_block == TIP

    def test_recovered_flag_does_not_pause_worker_outside_fallback(self, node_health):
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        pipeline.cp_nodes_healthy_again = True
        pipeline.last_health_check = time.time()
        assert pipeline.check_cp_node_recovery() is False

    def test_rollback_drains_session_using_indexed_height(self, near_tip_backend, node_health, monkeypatch):
        """Bitcoin tip far ahead of the indexer must not block recovery of a bounded session."""
        node_health.return_value = []
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        pipeline.current_block = TIP
        pipeline._enter_fallback_mode()
        for block_index in range(TIP, TIP + 5):
            pipeline.get_block(block_index)
            ReprocessingQueue.get_instance().add_failed_block(TIP, block_index)
        assert ReprocessingQueue.get_instance().get_fallback_stats()["total_failed_blocks"] == 5

        node_health.return_value = HEALTHY
        pipeline.last_health_check = 0
        assert pipeline.check_cp_node_recovery() is True

        near_tip_backend.getblockcount.return_value = TIP + 5000  # bitcoin kept moving
        monkeypatch.setattr("index_core.reprocess_safety.is_production_environment", lambda: True)
        with patch.object(CPBlocksPipeline, "_indexer_height_for_rollback", return_value=TIP + 4), patch(
            "index_core.database.perform_complete_rollback"
        ) as rollback, patch("index_core.blocks.notify_api_cache_invalidation"), patch.object(
            CPBlocksPipeline, "reset"
        ) as reset:
            assert pipeline.check_and_perform_rollback() is True

        rollback.assert_called_once_with(TIP, force=False)
        reset.assert_called_once_with(TIP)
        assert pipeline.fallback_started_at is None
        assert pipeline.failed_cp_blocks == set()
        assert pipeline.rollback_requested is False
        assert not _global_fallback_enabled()
        stats = ReprocessingQueue.get_instance().get_fallback_stats()
        assert stats["session_count"] == 0
        assert stats["total_failed_blocks"] == 0

    def test_rollback_still_refuses_beyond_safety_bound(self, near_tip_backend, node_health, monkeypatch):
        from index_core.reprocess_safety import MAX_ROLLBACK_BLOCKS

        node_health.return_value = []
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        pipeline.current_block = TIP
        pipeline._enter_fallback_mode()
        monkeypatch.setattr("index_core.reprocess_safety.is_production_environment", lambda: True)
        with patch.object(CPBlocksPipeline, "_indexer_height_for_rollback", return_value=TIP + MAX_ROLLBACK_BLOCKS + 1), patch(
            "index_core.database.perform_complete_rollback"
        ) as rollback:
            assert pipeline._perform_database_rollback(TIP) is False
        rollback.assert_not_called()
        assert pipeline.fallback_started_at == TIP


class TestReprocessingQueueDedupe:
    def test_add_failed_block_is_idempotent(self):
        queue = ReprocessingQueue.get_instance()
        for _ in range(50):
            for block_index in range(TIP, TIP + 10):
                queue.add_failed_block(TIP, block_index)
        stats = queue.get_fallback_stats()
        assert stats["session_count"] == 1
        assert stats["total_failed_blocks"] == 10
        assert queue.load_fallback_state(TIP) == {b: True for b in range(TIP, TIP + 10)}

    def test_save_fallback_state_keeps_session_id_and_leaves_no_orphans(self):
        queue = ReprocessingQueue.get_instance()
        state = {}
        session_ids = set()
        for block_index in range(TIP, TIP + 20):
            state[block_index] = True
            queue.save_fallback_state(TIP, dict(state))
            session_ids.add(queue.conn.execute("SELECT id FROM fallback_sessions").fetchone()[0])
        assert len(session_ids) == 1
        assert queue.conn.execute("SELECT COUNT(*) FROM failed_blocks").fetchone()[0] == 20

    def test_clear_fallback_state_cascades(self):
        queue = ReprocessingQueue.get_instance()
        for block_index in range(TIP, TIP + 5):
            queue.add_failed_block(TIP, block_index)
        queue.clear_fallback_state(TIP)
        assert queue.conn.execute("SELECT COUNT(*) FROM failed_blocks").fetchone()[0] == 0

    def test_orphan_rows_are_purged_on_open(self, isolated_queue):
        ReprocessingQueue._instance.close()
        ReprocessingQueue._instance = None
        conn = sqlite3.connect(isolated_queue)
        conn.execute("INSERT INTO fallback_sessions (start_block_index) VALUES (?)", (TIP,))
        live_id = conn.execute("SELECT id FROM fallback_sessions").fetchone()[0]
        conn.execute("INSERT INTO failed_blocks (session_id, block_index) VALUES (?, ?)", (live_id, TIP))
        for stale_id in range(live_id + 1, live_id + 6):
            conn.execute("INSERT INTO failed_blocks (session_id, block_index) VALUES (?, ?)", (stale_id, TIP))
        conn.commit()
        conn.close()

        ReprocessingQueue._instance = ReprocessingQueue(db_path=isolated_queue)
        queue = ReprocessingQueue.get_instance()
        assert queue.conn.execute("SELECT COUNT(*) FROM failed_blocks").fetchone()[0] == 1
        assert queue.load_fallback_state(TIP) == {TIP: True}
