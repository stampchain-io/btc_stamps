"""Regression tests for issue #957: fallback-processed blocks must be backfilled.

Companion to test_cp_fallback_tip_race.py (which covers fallback entry). These tests
cover what happens AFTER a block was indexed without Counterparty data:

- the block is re-served with its issuances once CP is back and the session closes;
- recovery is driven by the main loop, so it no longer depends on the fetch worker;
- a pipeline (re)started at the chain tip keeps its worker alive;
- an ageing session and a capped session raise ops alerts;
- the tip wait uses bounded backoff while CP is reachable and never falls back.
"""

from unittest.mock import patch

from src.index_core.pipeline_utils import CPBlocksPipeline
from src.index_core.reprocessing_queue import ReprocessingQueue
from tests import test_cp_fallback_tip_race as tip_race
from tests.test_cp_fallback_tip_race import (
    HEALTHY,
    ISSUANCE,
    TIP,
    _global_fallback_enabled,
    _run_worker,
    _stop_worker,
    _wait_until,
)

# Share the tip-race module's fixtures (own queue file per test, tip == block, CP health control).
isolated_queue = tip_race.isolated_queue
near_tip_backend = tip_race.near_tip_backend
node_health = tip_race.node_health


class TestBackfillRegression:
    def test_fallback_block_is_reprocessed_with_stamp_after_cp_recovers(self, near_tip_backend, node_health, monkeypatch):
        """Block indexed in fallback, CP later available: block re-served with its stamp, session closed."""
        node_health.return_value = []  # genuine outage at the tip
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, initial_fetch_size=1, fallback_mode=True)
        pipeline.fetch_interval = 0.01
        pipeline.current_block = TIP
        pipeline._enter_fallback_mode()

        # The processor takes the fallback block (no issuances) and records it, as blocks.follow does.
        fallback_block = pipeline.get_block(TIP)
        assert fallback_block["fallback_mode"] is True and fallback_block["issuances"] == []
        ReprocessingQueue.get_instance().add_failed_block(TIP, TIP)
        pipeline.confirm_block_processed(TIP)
        assert ReprocessingQueue.get_instance().get_fallback_stats()["total_failed_blocks"] == 1

        # Counterparty comes back with the block parsed. The main loop's rollback check must
        # notice on its own (no worker thread is running here), roll back, and restart the
        # pipeline; the real fetch worker then serves the block WITH its issuance.
        node_health.return_value = HEALTHY
        pipeline.last_health_check = 0
        monkeypatch.setattr("index_core.reprocess_safety.is_production_environment", lambda: True)

        def cp_fetch(start, end, **_kwargs):
            return {b: {"block_index": b, "issuances": [ISSUANCE] if b == TIP else []} for b in range(start, end + 1)}

        try:
            with patch.object(CPBlocksPipeline, "_indexer_height_for_rollback", return_value=TIP), patch(
                "index_core.database.perform_complete_rollback"
            ) as rollback, patch("index_core.blocks.notify_api_cache_invalidation"), patch(
                "src.index_core.pipeline_utils.wait_for_cp_block_processed", return_value=True
            ), patch(
                "src.index_core.pipeline_utils.fetch_cp_blocks_skipping_empty", side_effect=cp_fetch
            ):
                assert pipeline.check_and_perform_rollback() is True
                rollback.assert_called_once_with(TIP, force=False)

                assert _wait_until(lambda: pipeline.get_block(TIP) is not None)
                block = pipeline.get_block(TIP)
        finally:
            pipeline.stop()

        assert not block.get("fallback_mode")
        assert block["issuances"] == [ISSUANCE]
        assert pipeline.fallback_started_at is None
        assert pipeline.failed_cp_blocks == set()
        assert not _global_fallback_enabled()
        stats = ReprocessingQueue.get_instance().get_fallback_stats()
        assert stats["session_count"] == 0
        assert stats["total_failed_blocks"] == 0

    def test_main_loop_requests_recovery_without_worker_thread(self, near_tip_backend, node_health, monkeypatch):
        """Recovery used to depend on the worker thread; the main loop now drives it too."""
        node_health.return_value = []
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        pipeline.current_block = TIP
        pipeline._enter_fallback_mode()
        pipeline.get_block(TIP)
        assert pipeline.worker_thread is None

        node_health.return_value = HEALTHY
        pipeline.last_health_check = 0
        monkeypatch.setattr("index_core.reprocess_safety.is_production_environment", lambda: True)
        with patch.object(CPBlocksPipeline, "_indexer_height_for_rollback", return_value=TIP), patch(
            "index_core.database.perform_complete_rollback"
        ), patch("index_core.blocks.notify_api_cache_invalidation"), patch.object(CPBlocksPipeline, "reset") as reset:
            assert pipeline.check_and_perform_rollback() is True
        reset.assert_called_once_with(TIP)
        assert pipeline.fallback_started_at is None

    def test_recovery_check_not_run_when_no_session_open(self, near_tip_backend, node_health):
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        with patch.object(CPBlocksPipeline, "check_cp_node_recovery") as recovery:
            assert pipeline.check_and_perform_rollback() is False
        recovery.assert_not_called()

    def test_start_at_tip_still_runs_worker(self, near_tip_backend, node_health):
        """A pipeline (re)started while caught up must keep its worker so recovery can fire."""
        near_tip_backend.getblockcount.return_value = TIP - 1  # nothing to prefetch yet
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        pipeline.fetch_interval = 0.01
        try:
            pipeline.start(TIP)
            assert pipeline.initial_blocks_ready.is_set()
            assert pipeline.worker_thread is not None and pipeline.worker_thread.is_alive()
            assert pipeline.fallback_started_at is None
        finally:
            pipeline.stop()


class TestFallbackAlerts:
    def test_ageing_session_alerts(self, near_tip_backend, node_health, monkeypatch):
        monkeypatch.setenv("CP_FALLBACK_ALERT_AFTER_BLOCKS", "2")
        node_health.return_value = []
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        pipeline.current_block = TIP
        with patch("index_core.ops_alerter.notify", return_value=True) as notify:
            pipeline._enter_fallback_mode()  # pre-creates 5 blocks; blocks TIP+2.. are past the threshold
            assert notify.call_count == 3
            pipeline.queue.clear()
            notify.reset_mock()
            pipeline.get_block(TIP)
            pipeline.get_block(TIP + 1)
            notify.assert_not_called()
            pipeline.get_block(TIP + 2)
        assert notify.call_count == 1
        assert notify.call_args.args[0] == "critical"
        assert notify.call_args.kwargs["dedup_key"] == f"fallback-session-{TIP}"

    def test_session_cap_alerts_once(self, near_tip_backend, node_health, monkeypatch):
        monkeypatch.setenv("CP_FALLBACK_MAX_SESSION_BLOCKS", "2")
        monkeypatch.setenv("CP_FALLBACK_ALERT_AFTER_BLOCKS", "999")
        node_health.return_value = []
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, fallback_mode=True)
        pipeline.current_block = TIP
        with patch("index_core.ops_alerter.notify", return_value=True) as notify:
            pipeline._enter_fallback_mode()  # tries to pre-create 5 blocks, hits the cap at the third
            assert notify.call_count == 1
            assert notify.call_args.args[0] == "critical"
            assert notify.call_args.kwargs["dedup_key"] == f"fallback-cap-{TIP}"
            pipeline.queue.clear()
            assert pipeline.get_block(TIP) is not None
            assert pipeline.get_block(TIP + 1) is not None
            assert pipeline.get_block(TIP + 2) is None
            assert pipeline.get_block(TIP + 2) is None
        assert notify.call_count == 1  # the cap alert is raised once per session


class TestTipWaitBackoff:
    def test_cp_reachable_but_behind_waits_with_backoff(self, near_tip_backend, node_health, monkeypatch):
        """The worker's tip wait times out repeatedly while CP answers: back off, never fall back."""
        monkeypatch.setenv("CP_BEHIND_BACKOFF_INITIAL_SEC", "0.01")
        monkeypatch.setenv("CP_BEHIND_BACKOFF_MAX_SEC", "0.02")
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, initial_fetch_size=1, fallback_mode=True)
        pipeline.fetch_interval = 0.01
        with patch("src.index_core.pipeline_utils.wait_for_cp_block_processed", return_value=False), patch(
            "src.index_core.pipeline_utils.fetch_cp_blocks_skipping_empty"
        ) as fetch:
            thread = _run_worker(pipeline, TIP)
            try:
                assert _wait_until(lambda: pipeline._cp_behind.attempts >= 3)
                assert pipeline.fallback_started_at is None
                assert not _global_fallback_enabled()
                assert pipeline.get_block(TIP) is None
                fetch.assert_not_called()
            finally:
                _stop_worker(pipeline, thread)
        assert ReprocessingQueue.get_instance().get_fallback_stats()["session_count"] == 0

    def test_tip_wait_timeout_with_no_reachable_node_enters_fallback(self, near_tip_backend, node_health):
        node_health.return_value = []
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, initial_fetch_size=1, fallback_mode=True)
        pipeline.fetch_interval = 0.01
        with patch("src.index_core.pipeline_utils.wait_for_cp_block_processed", return_value=False), patch(
            "src.index_core.pipeline_utils.fetch_cp_blocks_skipping_empty"
        ):
            thread = _run_worker(pipeline, TIP)
            try:
                assert _wait_until(lambda: pipeline.fallback_started_at is not None)
                assert pipeline.fallback_started_at == TIP
                assert pipeline._cp_behind.attempts == 0
            finally:
                _stop_worker(pipeline, thread)

    def test_tip_wait_timeout_is_taken_from_env(self, near_tip_backend, node_health, monkeypatch):
        monkeypatch.setenv("CP_TIP_WAIT_TIMEOUT", "7")
        monkeypatch.setenv("CP_BEHIND_BACKOFF_INITIAL_SEC", "0.01")
        monkeypatch.setenv("CP_BEHIND_BACKOFF_MAX_SEC", "0.01")
        pipeline = CPBlocksPipeline(max_queue_size=10, target_queue_size=5, initial_fetch_size=1, fallback_mode=True)
        pipeline.fetch_interval = 0.01
        with patch("src.index_core.pipeline_utils.wait_for_cp_block_processed", return_value=False) as wait, patch(
            "src.index_core.pipeline_utils.fetch_cp_blocks_skipping_empty"
        ):
            thread = _run_worker(pipeline, TIP)
            try:
                assert _wait_until(lambda: wait.call_count >= 1)
            finally:
                _stop_worker(pipeline, thread)
        assert wait.call_args.kwargs["max_wait"] == 7.0
