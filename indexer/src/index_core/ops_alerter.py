"""Operational alerter for unrecoverable / loop-pattern incidents.

Publishes structured alerts to an SNS topic when the indexer detects
patterns it cannot recover from autonomously (stuck rollback loops,
silent hangs, etc). All routing is controlled by the
``OPS_ALERT_SNS_TOPIC_ARN`` environment variable — when unset, the
module silently no-ops, so dev/CI environments are not affected and
no AWS account-specific identifiers live in the repo.

Dedup / rate-limit: each ``notify()`` call carries a ``dedup_key``;
repeats of the same key within ``OPS_ALERT_DEDUP_WINDOW_SEC`` (default
3600s = 1h) are suppressed to avoid paging storms during sustained
incidents.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Module-level state (process-wide; the indexer is single-process).
_dedup_lock = threading.Lock()
_last_notified: Dict[str, float] = {}
_sns_client = None  # lazy-initialized
_sns_init_lock = threading.Lock()


def _get_dedup_window_sec() -> int:
    try:
        return int(os.environ.get("OPS_ALERT_DEDUP_WINDOW_SEC", "3600"))
    except ValueError:
        return 3600


def _get_topic_arn() -> Optional[str]:
    arn = os.environ.get("OPS_ALERT_SNS_TOPIC_ARN", "").strip()
    return arn or None


def _get_sns_client():
    """Lazy boto3 SNS client. Returns None if boto3 missing or topic not set."""
    global _sns_client
    if _sns_client is not None:
        return _sns_client
    with _sns_init_lock:
        if _sns_client is not None:
            return _sns_client
        try:
            import boto3  # type: ignore

            region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
            _sns_client = boto3.client("sns", region_name=region)
        except Exception as e:
            logger.debug(f"ops_alerter: boto3 init failed ({e}); alerts will be log-only")
            _sns_client = False  # sentinel so we don't retry every call
    return _sns_client if _sns_client else None


def notify(severity: str, title: str, body: str, dedup_key: str) -> bool:
    """Publish an operational alert.

    Returns True if a publish was attempted, False if suppressed (dedup
    window) or no-op (no topic configured).

    severity: one of ``critical``, ``warning``, ``info`` — included in
        the subject line for downstream filtering. SMS-deliverable
        subject is truncated to 100 chars to fit AWS SNS limits.
    dedup_key: stable identifier; second call with the same key within
        OPS_ALERT_DEDUP_WINDOW_SEC is suppressed.
    """
    now = time.monotonic()
    window = _get_dedup_window_sec()

    with _dedup_lock:
        last = _last_notified.get(dedup_key, 0.0)
        if last and (now - last) < window:
            logger.debug(f"ops_alerter: suppressing duplicate alert {dedup_key} ({int(now - last)}s since last)")
            return False
        _last_notified[dedup_key] = now

    topic = _get_topic_arn()
    if not topic:
        # No topic configured — log at WARNING so the alert is at least
        # visible in journald/CloudWatch logs.
        logger.warning(f"OPS_ALERT [{severity}] {title} | {body[:500]}")
        return False

    hostname = socket.gethostname()
    subject = f"[{severity.upper()}] stamps-indexer: {title}"[:100]
    message = f"host: {hostname}\nseverity: {severity}\ndedup_key: {dedup_key}\n\n{body}"

    client = _get_sns_client()
    if client is None:
        logger.warning(f"OPS_ALERT [{severity}] {title} | {body[:500]} (sns_unavailable)")
        return False

    try:
        client.publish(TopicArn=topic, Subject=subject, Message=message)
        logger.info(f"ops_alerter: published {dedup_key} → SNS")
        return True
    except Exception as e:
        logger.error(f"ops_alerter: SNS publish failed for {dedup_key}: {e}")
        return False


# ---------------------------------------------------------------------------
# Pattern detectors
# ---------------------------------------------------------------------------


class StuckRollbackDetector:
    """Detect when the same target block has been rolled back to repeatedly
    in a short window — the classic CP/BTC hash-mismatch loop where each
    reparse hits the same divergent block and rolls back again.
    """

    def __init__(self, window_sec: int = 1800, threshold: int = 3):
        self.window_sec = window_sec
        self.threshold = threshold
        self._events: Dict[int, list] = {}
        self._lock = threading.Lock()

    def record(self, target_block: int, reason: str) -> None:
        now = time.monotonic()
        with self._lock:
            events = self._events.setdefault(target_block, [])
            events.append(now)
            # prune outside the window
            cutoff = now - self.window_sec
            events[:] = [t for t in events if t >= cutoff]
            count = len(events)

        if count >= self.threshold:
            notify(
                "critical",
                f"Stuck rollback loop at block {target_block}",
                (
                    f"Indexer rolled back to block {target_block} {count} times in the "
                    f"last {self.window_sec // 60} minutes. Reason: {reason}. Likely a "
                    f"CP/BTC divergence — CP node may need manual rollback "
                    f"(`counterparty-core rollback <block_before_mismatch>`)."
                ),
                dedup_key=f"stuck-rollback-{target_block}",
            )


class ProgressWatchdog:
    """Background thread that fires an alert if the main indexer loop
    hasn't ticked in ``stall_threshold_sec``. Mirrors the May-23 silent
    hang where systemd reported active(running) but no log output for
    24 hours.
    """

    def __init__(self, stall_threshold_sec: Optional[int] = None, check_interval_sec: int = 60):
        # Threshold is configurable via OPS_ALERT_STALL_SEC (default 1800s) so it
        # can be tuned per-deployment without a code change. An explicit arg still
        # wins (used by tests).
        self.stall_threshold_sec = (
            stall_threshold_sec if stall_threshold_sec is not None else int(os.environ.get("OPS_ALERT_STALL_SEC", "1800"))
        )
        self.check_interval_sec = check_interval_sec
        self._last_tick = time.monotonic()
        self._last_tick_label = "startup"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def tick(self, label: str = "") -> None:
        """Call from the main loop on each block (or any progress event)."""
        with self._lock:
            self._last_tick = time.monotonic()
            if label:
                self._last_tick_label = label

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="ops-progress-watchdog", daemon=True)
        self._thread.start()
        logger.info(
            f"ops_alerter: ProgressWatchdog started "
            f"(stall_threshold={self.stall_threshold_sec}s, check={self.check_interval_sec}s)"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.wait(self.check_interval_sec):
            with self._lock:
                stalled_for = time.monotonic() - self._last_tick
                label = self._last_tick_label
            if stalled_for >= self.stall_threshold_sec:
                notify(
                    "critical",
                    "Indexer progress watchdog tripped",
                    (
                        f"No main-loop progress for {int(stalled_for)}s "
                        f"(threshold {self.stall_threshold_sec}s). "
                        f"Last progress label: {label}. "
                        f"Process may be hung — consider `systemctl restart btc-stamps-indexer`."
                    ),
                    dedup_key="progress-watchdog",
                )


# Singletons for the indexer to import.
stuck_rollback_detector = StuckRollbackDetector()
progress_watchdog = ProgressWatchdog()
