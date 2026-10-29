"""Tests for index_core.fallback_monitor (issue #957).

Covers the session-age alert, the cap alert, the bounded backoff used while
Counterparty is reachable but behind, and the startup report of persisted
fallback sessions.
"""

from unittest.mock import patch

import pytest

# fallback_monitor imports index_core.* absolutely, so the queue singleton it reads is the
# index_core copy; import the same copy here (not src.index_core) so the fixture and the
# code under test share one ReprocessingQueue class.
from index_core import fallback_monitor
from index_core.reprocess_safety import MAX_ROLLBACK_BLOCKS
from index_core.reprocessing_queue import ReprocessingQueue

START = 969004


@pytest.fixture(autouse=True)
def isolated_queue(tmp_path):
    """Each test gets its own reprocessing queue file."""
    if ReprocessingQueue._instance is not None:
        try:
            ReprocessingQueue._instance.close()
        except Exception:
            pass
    ReprocessingQueue._instance = None
    ReprocessingQueue._instance = ReprocessingQueue(db_path=str(tmp_path / "reprocess_queue.db"))
    yield ReprocessingQueue._instance
    if ReprocessingQueue._instance is not None:
        ReprocessingQueue._instance.close()
    ReprocessingQueue._instance = None


@pytest.fixture
def notify():
    with patch("index_core.ops_alerter.notify", return_value=True) as mock_notify:
        yield mock_notify


class TestSessionAlerts:
    def test_young_session_does_not_alert(self, notify, monkeypatch):
        monkeypatch.setenv("CP_FALLBACK_ALERT_AFTER_BLOCKS", "6")
        assert fallback_monitor.on_fallback_block(START, START + 5) is False
        notify.assert_not_called()

    def test_session_at_threshold_alerts_critical_with_stable_key(self, notify, monkeypatch):
        monkeypatch.setenv("CP_FALLBACK_ALERT_AFTER_BLOCKS", "6")
        assert fallback_monitor.on_fallback_block(START, START + 6) is True
        severity, title, body = notify.call_args.args
        assert severity == "critical"
        assert str(START) in title
        assert "6 blocks old" in body
        assert notify.call_args.kwargs["dedup_key"] == f"fallback-session-{START}"

    def test_threshold_is_configurable(self, notify, monkeypatch):
        monkeypatch.setenv("CP_FALLBACK_ALERT_AFTER_BLOCKS", "1")
        assert fallback_monitor.on_fallback_block(START, START + 1) is True

    def test_cap_alert(self, notify):
        assert fallback_monitor.on_session_cap_reached(START, START + 990, 990) is True
        assert notify.call_args.args[0] == "critical"
        assert notify.call_args.kwargs["dedup_key"] == f"fallback-cap-{START}"

    def test_recovered_alert_is_info(self, notify):
        fallback_monitor.on_session_recovered(START, 12)
        assert notify.call_args.args[0] == "info"
        assert "12 blocks" in notify.call_args.args[2]

    def test_alert_failure_does_not_raise(self):
        with patch("index_core.ops_alerter.notify", side_effect=RuntimeError("sns down")):
            assert fallback_monitor.on_fallback_block(START, START + 100) is False


class TestCPBehindTracker:
    def test_backoff_is_bounded_exponential(self, notify, monkeypatch):
        monkeypatch.setenv("CP_BEHIND_BACKOFF_INITIAL_SEC", "1")
        monkeypatch.setenv("CP_BEHIND_BACKOFF_MAX_SEC", "4")
        monkeypatch.setenv("CP_BEHIND_ALERT_AFTER_SEC", "99999")
        tracker = fallback_monitor.CPBehindTracker()
        delays = [tracker.note_behind(START) for _ in range(5)]
        assert delays == [1.0, 2.0, 4.0, 4.0, 4.0]
        assert tracker.attempts == 5
        notify.assert_not_called()

    def test_reset_starts_a_new_episode(self, notify, monkeypatch):
        monkeypatch.setenv("CP_BEHIND_BACKOFF_INITIAL_SEC", "1")
        monkeypatch.setenv("CP_BEHIND_BACKOFF_MAX_SEC", "60")
        tracker = fallback_monitor.CPBehindTracker()
        tracker.note_behind(START)
        tracker.note_behind(START)
        tracker.reset()
        assert tracker.attempts == 0
        assert tracker.episode_seconds() == 0.0
        assert tracker.note_behind(START) == 1.0

    def test_alerts_once_per_episode_after_grace(self, notify, monkeypatch):
        monkeypatch.setenv("CP_BEHIND_BACKOFF_INITIAL_SEC", "0")
        monkeypatch.setenv("CP_BEHIND_ALERT_AFTER_SEC", "0")
        tracker = fallback_monitor.CPBehindTracker()
        tracker.note_behind(START, cp_height=START - 1)
        tracker.note_behind(START, cp_height=START - 1)
        assert notify.call_count == 1
        assert notify.call_args.args[0] == "critical"
        assert notify.call_args.kwargs["dedup_key"] == "cp-behind-tip"
        tracker.reset()
        tracker.note_behind(START)
        assert notify.call_count == 2

    def test_tip_wait_timeout_is_configurable(self, monkeypatch):
        assert fallback_monitor.tip_wait_timeout() == 180.0
        monkeypatch.setenv("CP_TIP_WAIT_TIMEOUT", "30")
        assert fallback_monitor.tip_wait_timeout() == 30.0
        monkeypatch.setenv("CP_TIP_WAIT_TIMEOUT", "garbage")
        assert fallback_monitor.tip_wait_timeout() == 180.0


class TestStartupReport:
    def test_no_session(self, notify, isolated_queue):
        result = fallback_monitor.report_fallback_state_at_startup(START + 10)
        assert result == {"sessions": [], "unrecoverable": [], "error": None}
        notify.assert_not_called()

    def test_recoverable_session_is_reported_not_alerted(self, notify, isolated_queue):
        for block in range(START, START + 5):
            isolated_queue.add_failed_block(START, block)
        result = fallback_monitor.report_fallback_state_at_startup(START + 4)
        assert result["unrecoverable"] == []
        (session,) = result["sessions"]
        assert session["start_block_index"] == START
        assert session["block_count"] == 5
        assert session["first_block"] == START
        assert session["last_block"] == START + 4
        assert session["blocks_behind_indexer"] == 4
        assert session["recoverable_by_rollback"] is True
        notify.assert_not_called()

    def test_unrecoverable_session_alerts_critical(self, notify, isolated_queue):
        isolated_queue.add_failed_block(START, START)
        height = START + MAX_ROLLBACK_BLOCKS + 1
        result = fallback_monitor.report_fallback_state_at_startup(height)
        assert result["unrecoverable"] == [START]
        assert result["sessions"][0]["recoverable_by_rollback"] is False
        severity, title, body = notify.call_args.args
        assert severity == "critical"
        assert str(START) in title
        assert "drain_fallback_queue.py" in body
        assert notify.call_args.kwargs["dedup_key"] == f"fallback-unrecoverable-{START}"

    def test_unknown_height_reports_without_verdict(self, notify, isolated_queue):
        isolated_queue.add_failed_block(START, START)
        result = fallback_monitor.report_fallback_state_at_startup(None)
        assert result["sessions"][0]["recoverable_by_rollback"] is None
        assert result["unrecoverable"] == []
        notify.assert_not_called()

    def test_queue_error_is_reported_not_raised(self, notify):
        with patch.object(ReprocessingQueue, "list_sessions", side_effect=RuntimeError("locked")):
            result = fallback_monitor.report_fallback_state_at_startup(START)
        assert result["error"] == "RuntimeError: locked"
        assert result["sessions"] == []


class TestQueueListSessions:
    def test_list_sessions_counts_and_ranges(self, isolated_queue):
        assert isolated_queue.list_sessions() == []
        for block in (START, START + 2, START + 7):
            isolated_queue.add_failed_block(START, block)
        isolated_queue.add_failed_block(START + 100, START + 100)
        sessions = isolated_queue.list_sessions()
        assert [s["start_block_index"] for s in sessions] == [START, START + 100]
        assert sessions[0]["block_count"] == 3
        assert (sessions[0]["first_block"], sessions[0]["last_block"]) == (START, START + 7)
        assert sessions[1]["block_count"] == 1
