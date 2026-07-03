"""Unit tests for index_core.ops_alerter."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from index_core import ops_alerter


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Reset module-level state between tests."""
    ops_alerter._last_notified.clear()
    ops_alerter._sns_client = None
    monkeypatch.delenv("OPS_ALERT_SNS_TOPIC_ARN", raising=False)
    monkeypatch.delenv("OPS_ALERT_DEDUP_WINDOW_SEC", raising=False)
    yield
    ops_alerter._last_notified.clear()
    ops_alerter._sns_client = None


def test_notify_noop_when_topic_unset(caplog):
    """Without OPS_ALERT_SNS_TOPIC_ARN, notify() logs but returns False."""
    with caplog.at_level("WARNING"):
        result = ops_alerter.notify("critical", "x", "body", "k1")
    assert result is False
    assert any("OPS_ALERT" in r.message for r in caplog.records)


def test_notify_publishes_when_topic_set(monkeypatch):
    monkeypatch.setenv("OPS_ALERT_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:000:topic")
    mock_client = MagicMock()
    monkeypatch.setattr(ops_alerter, "_get_sns_client", lambda: mock_client)

    result = ops_alerter.notify("critical", "t", "b", "k2")
    assert result is True
    mock_client.publish.assert_called_once()
    kwargs = mock_client.publish.call_args.kwargs
    assert kwargs["TopicArn"] == "arn:aws:sns:us-east-1:000:topic"
    assert "[CRITICAL]" in kwargs["Subject"]
    assert "k2" in kwargs["Message"]


def test_dedup_suppresses_repeat_within_window(monkeypatch):
    monkeypatch.setenv("OPS_ALERT_SNS_TOPIC_ARN", "arn:x")
    monkeypatch.setenv("OPS_ALERT_DEDUP_WINDOW_SEC", "60")
    mock_client = MagicMock()
    monkeypatch.setattr(ops_alerter, "_get_sns_client", lambda: mock_client)

    assert ops_alerter.notify("warn", "a", "b", "samekey") is True
    assert ops_alerter.notify("warn", "a", "b", "samekey") is False  # suppressed
    assert ops_alerter.notify("warn", "a", "b", "differentkey") is True
    assert mock_client.publish.call_count == 2


def test_dedup_allows_after_window(monkeypatch):
    monkeypatch.setenv("OPS_ALERT_SNS_TOPIC_ARN", "arn:x")
    monkeypatch.setenv("OPS_ALERT_DEDUP_WINDOW_SEC", "1")
    mock_client = MagicMock()
    monkeypatch.setattr(ops_alerter, "_get_sns_client", lambda: mock_client)

    assert ops_alerter.notify("info", "x", "y", "k") is True
    # Simulate window passing by rewriting the recorded timestamp
    ops_alerter._last_notified["k"] = time.monotonic() - 2
    assert ops_alerter.notify("info", "x", "y", "k") is True
    assert mock_client.publish.call_count == 2


def test_stuck_rollback_detector_fires_at_threshold(monkeypatch):
    fired = []
    monkeypatch.setattr(ops_alerter, "notify", lambda *a, **kw: fired.append((a, kw)))

    det = ops_alerter.StuckRollbackDetector(window_sec=60, threshold=3)
    det.record(951050, "test")
    det.record(951050, "test")
    assert fired == []
    det.record(951050, "test")
    assert len(fired) == 1
    args, kwargs = fired[0]
    assert args[0] == "critical"
    assert kwargs["dedup_key"] == "stuck-rollback-951050"


def test_stuck_rollback_detector_different_targets_independent(monkeypatch):
    fired = []
    monkeypatch.setattr(ops_alerter, "notify", lambda *a, **kw: fired.append((a, kw)))

    det = ops_alerter.StuckRollbackDetector(window_sec=60, threshold=2)
    det.record(100, "x")
    det.record(200, "x")
    det.record(300, "x")
    assert fired == []
    det.record(100, "x")
    assert len(fired) == 1


def test_progress_watchdog_ticks_reset_timer(monkeypatch):
    fired = []
    monkeypatch.setattr(ops_alerter, "notify", lambda *a, **kw: fired.append(a))

    wd = ops_alerter.ProgressWatchdog(stall_threshold_sec=1, check_interval_sec=1)
    # Don't start the background thread — exercise the internal logic directly.
    wd.tick("block 1")
    initial = wd._last_tick
    time.sleep(0.01)
    wd.tick("block 2")
    assert wd._last_tick > initial
    assert wd._last_tick_label == "block 2"


def test_get_sns_client_handles_missing_boto3(monkeypatch):
    """If boto3 isn't installed, _get_sns_client should return None gracefully."""
    monkeypatch.setattr(ops_alerter, "_sns_client", None)

    # Force ImportError on boto3
    import builtins

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("simulated missing boto3")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert ops_alerter._get_sns_client() is None


def test_watchdog_threshold_from_env(monkeypatch):
    """OPS_ALERT_STALL_SEC configures the stall threshold; explicit arg still wins."""
    monkeypatch.delenv("OPS_ALERT_STALL_SEC", raising=False)
    assert ops_alerter.ProgressWatchdog().stall_threshold_sec == 1800  # default

    monkeypatch.setenv("OPS_ALERT_STALL_SEC", "3600")
    assert ops_alerter.ProgressWatchdog().stall_threshold_sec == 3600  # env honored

    # An explicit constructor arg overrides the env (used by tests/callers).
    assert ops_alerter.ProgressWatchdog(stall_threshold_sec=42).stall_threshold_sec == 42


def test_watchdog_tick_resets_stall_timer():
    """Idle-at-tip fix: ticking during a healthy wait clears the stall timer so the
    watchdog does NOT trip; without a tick the timer keeps aging toward the trip.

    This models the blocks.py idle-at-tip wait loops, which now tick every poll/zmq
    iteration so normal Bitcoin inter-block gaps no longer false-trip the watchdog.
    """
    wd = ops_alerter.ProgressWatchdog(stall_threshold_sec=100)

    # Simulate a long wait with no progress -> the trip condition is met.
    wd._last_tick = time.monotonic() - 200
    assert (time.monotonic() - wd._last_tick) >= wd.stall_threshold_sec

    # A single idle-at-tip tick clears the stall -> would NOT trip.
    wd.tick(label="at tip 956514, waiting for next block (poll)")
    assert (time.monotonic() - wd._last_tick) < wd.stall_threshold_sec
    assert wd._last_tick_label == "at tip 956514, waiting for next block (poll)"


def test_watchdog_fires_when_no_tick_past_threshold(monkeypatch):
    """When the main loop genuinely stops ticking past the threshold, the watchdog
    still fires a critical alert (the real-hang case must survive the idle-at-tip fix)."""
    fired = []
    monkeypatch.setattr(ops_alerter, "notify", lambda *a, **kw: fired.append(kw.get("dedup_key")))

    # threshold 0 -> any elapsed time counts as stalled; fast check interval.
    wd = ops_alerter.ProgressWatchdog(stall_threshold_sec=0, check_interval_sec=0.01)
    wd.start()
    time.sleep(0.1)
    wd.stop()

    assert "progress-watchdog" in fired
