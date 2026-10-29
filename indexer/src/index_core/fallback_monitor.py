"""Observability for Counterparty fallback sessions (issue #957).

Fallback mode lets the indexer keep following the chain while every Counterparty
node is down. Each block processed that way is recorded in a *fallback session*
in the reprocessing queue and must be redone with CP data once CP is back. In
production a session stayed open for five weeks without anyone noticing, because
nothing alerted on an ageing session and nothing reported the session state at
startup. This module adds that visibility and the bounded wait used while CP is
reachable but has not yet parsed the tip block.

Everything here is observability or pacing: nothing in this module decides what
a block contains, so it is consensus-neutral.

Environment knobs (read at call time so tests and operators can change them
without a restart of the Python module):

``CP_FALLBACK_ALERT_AFTER_BLOCKS``   alert once an open session is this many blocks
                                      behind the block being indexed (default 6).
``CP_TIP_WAIT_TIMEOUT``              seconds one CP readiness wait near the tip may
                                      take before the worker re-evaluates (default 180).
``CP_BEHIND_BACKOFF_INITIAL_SEC``    first retry delay while CP is reachable but
                                      behind (default 5).
``CP_BEHIND_BACKOFF_MAX_SEC``        cap on that delay (default 60).
``CP_BEHIND_ALERT_AFTER_SEC``        alert once CP has been continuously reachable
                                      but behind for this long (default 1800).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from index_core.reprocess_safety import MAX_ROLLBACK_BLOCKS

logger = logging.getLogger(__name__)

DRAIN_TOOL_HINT = "cd indexer && poetry run python tools/drain_fallback_queue.py --status"


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, value)


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, value)


def fallback_alert_after_blocks() -> int:
    return _env_int("CP_FALLBACK_ALERT_AFTER_BLOCKS", 6, minimum=1)


def tip_wait_timeout() -> float:
    return _env_float("CP_TIP_WAIT_TIMEOUT", 180.0, minimum=1.0)


def _notify(severity: str, title: str, body: str, dedup_key: str) -> bool:
    """Route through ops_alerter; an alert failure must never stop indexing."""
    try:
        from index_core.ops_alerter import notify

        return notify(severity, title, body, dedup_key=dedup_key)
    except Exception as alert_err:
        logger.error(f"ops_alerter notify failed for {dedup_key}: {type(alert_err).__name__}: {alert_err}")
        return False


# ---------------------------------------------------------------------------
# Fallback session alerts
# ---------------------------------------------------------------------------


def on_fallback_block(session_start: int, block_index: int) -> bool:
    """Called for every block handed out without CP data.

    Fires a critical alert once the session is ``CP_FALLBACK_ALERT_AFTER_BLOCKS``
    blocks old. ops_alerter dedups by key, so the alert repeats once per dedup
    window for as long as the session stays open. Returns True when an alert was
    attempted.
    """
    age = block_index - session_start
    threshold = fallback_alert_after_blocks()
    if age < threshold:
        return False
    return _notify(
        "critical",
        f"Fallback session open since block {session_start}",
        (
            f"Block {block_index} is being indexed without Counterparty data; the fallback session that "
            f"started at block {session_start} is {age} blocks old (alert threshold {threshold}). Every block in "
            f"it is missing its stamp issuances until the recovery rollback runs. Check that a Counterparty node "
            f"is reachable. Session state: {DRAIN_TOOL_HINT}"
        ),
        dedup_key=f"fallback-session-{session_start}",
    )


def on_session_cap_reached(session_start: int, block_index: int, cap: int) -> bool:
    """The session hit its recoverable cap and the indexer halted at ``block_index``."""
    return _notify(
        "critical",
        f"Fallback session at cap, indexer halted at block {block_index}",
        (
            f"The fallback session that started at block {session_start} reached its cap of {cap} blocks. The "
            f"indexer is holding at block {block_index} until Counterparty recovers, because a longer session "
            f"could no longer be rolled back and redone with CP data. Restore a Counterparty node; the recovery "
            f"rollback then runs on its own. Session state: {DRAIN_TOOL_HINT}"
        ),
        dedup_key=f"fallback-cap-{session_start}",
    )


def on_session_recovered(session_start: int, block_count: int) -> None:
    """The recovery rollback ran and the session was closed."""
    logger.warning(
        f"Fallback session that started at block {session_start} closed: {block_count} blocks rolled back and "
        f"being re-indexed with Counterparty data"
    )
    _notify(
        "info",
        f"Fallback session from block {session_start} recovered",
        f"{block_count} blocks processed without Counterparty data were rolled back and are being re-indexed.",
        dedup_key=f"fallback-recovered-{session_start}",
    )


# ---------------------------------------------------------------------------
# CP reachable but behind the tip: bounded backoff + alert
# ---------------------------------------------------------------------------


class CPBehindTracker:
    """Pace retries while Counterparty answers but has not parsed a block yet.

    A reachable CP that is a block behind is not an outage, so fallback must not
    start (that is the #957 trigger). The worker waits instead. Successive waits
    back off exponentially from ``CP_BEHIND_BACKOFF_INITIAL_SEC`` up to
    ``CP_BEHIND_BACKOFF_MAX_SEC`` and, once the episode has lasted
    ``CP_BEHIND_ALERT_AFTER_SEC``, a critical alert is raised so an operator looks
    at the CP node. ``reset()`` ends the episode when CP catches up.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._episode_started: Optional[float] = None
        self._attempts = 0
        self._alerted = False

    @property
    def attempts(self) -> int:
        with self._lock:
            return self._attempts

    def episode_seconds(self) -> float:
        with self._lock:
            if self._episode_started is None:
                return 0.0
            return time.monotonic() - self._episode_started

    def note_behind(self, block_index: int, cp_height: Optional[int] = None) -> float:
        """Record one more 'CP not ready' observation and return the delay to wait.

        The delay is bounded exponential backoff with no jitter so it is predictable
        in logs and tests.
        """
        initial = _env_float("CP_BEHIND_BACKOFF_INITIAL_SEC", 5.0, minimum=0.0)
        maximum = _env_float("CP_BEHIND_BACKOFF_MAX_SEC", 60.0, minimum=0.0)
        alert_after = _env_float("CP_BEHIND_ALERT_AFTER_SEC", 1800.0, minimum=0.0)

        with self._lock:
            now = time.monotonic()
            if self._episode_started is None:
                self._episode_started = now
                self._attempts = 0
                self._alerted = False
            self._attempts += 1
            attempts = self._attempts
            elapsed = now - self._episode_started
            should_alert = elapsed >= alert_after and not self._alerted
            if should_alert:
                self._alerted = True

        delay = min(initial * (2 ** (attempts - 1)), maximum) if initial > 0 else 0.0
        behind = f", CP at {cp_height}" if cp_height is not None else ""
        logger.warning(
            f"Counterparty is reachable but has not served block {block_index}{behind}; waiting {delay:.0f}s "
            f"(attempt {attempts}, {elapsed:.0f}s so far) instead of entering fallback mode"
        )
        if should_alert:
            _notify(
                "critical",
                f"Counterparty behind tip for {int(elapsed // 60)} minutes",
                (
                    f"Counterparty answers health checks but has not served block {block_index} for {int(elapsed)}s "
                    f"({attempts} attempts). The indexer is waiting rather than indexing without CP data. Check the "
                    f"Counterparty node's sync state."
                ),
                dedup_key="cp-behind-tip",
            )
        return delay

    def reset(self) -> None:
        with self._lock:
            if self._episode_started is not None and self._attempts:
                logger.info(
                    f"Counterparty caught up after {time.monotonic() - self._episode_started:.0f}s "
                    f"({self._attempts} waits)"
                )
            self._episode_started = None
            self._attempts = 0
            self._alerted = False


# ---------------------------------------------------------------------------
# Startup report
# ---------------------------------------------------------------------------


def summarize_sessions(sessions: List[Dict[str, Any]], indexer_height: Optional[int]) -> List[Dict[str, Any]]:
    """Annotate raw session rows with age and whether the recovery rollback can still run."""
    summary = []
    for session in sessions:
        start = int(session["start_block_index"])
        entry = dict(session)
        if indexer_height is None:
            entry["blocks_behind_indexer"] = None
            entry["recoverable_by_rollback"] = None
        else:
            behind = indexer_height - start
            entry["blocks_behind_indexer"] = behind
            entry["recoverable_by_rollback"] = behind <= MAX_ROLLBACK_BLOCKS
        summary.append(entry)
    return summary


def report_fallback_state_at_startup(indexer_height: Optional[int]) -> Dict[str, Any]:
    """Log, and if needed alert on, the persisted fallback state before indexing starts.

    Returns a dict with ``sessions`` (annotated) and ``unrecoverable`` (session
    starts the rollback bound can no longer reach). Never raises: a broken queue
    file is reported, not fatal, because the pipeline reports it again on its own.
    """
    result: Dict[str, Any] = {"sessions": [], "unrecoverable": [], "error": None}
    try:
        from index_core.reprocessing_queue import ReprocessingQueue

        queue = ReprocessingQueue.get_instance()
        sessions = summarize_sessions(queue.list_sessions(), indexer_height)
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        logger.error(f"Could not read fallback session state at startup: {result['error']}")
        return result

    result["sessions"] = sessions
    if not sessions:
        logger.info("Fallback state at startup: no open fallback session")
        return result

    for session in sessions:
        start = session["start_block_index"]
        count = session["block_count"]
        behind = session["blocks_behind_indexer"]
        recoverable = session["recoverable_by_rollback"]
        logger.warning(
            f"Fallback state at startup: open session from block {start} with {count} blocks "
            f"({'unknown' if behind is None else behind} blocks behind the indexer, "
            f"first={session['first_block']}, last={session['last_block']}, updated={session['updated_at']})"
        )
        if recoverable is False:
            result["unrecoverable"].append(start)
            logger.error(
                f"Fallback session from block {start} is {behind} blocks behind the indexer, beyond the "
                f"{MAX_ROLLBACK_BLOCKS}-block rollback bound. The startup rollback will refuse it and the indexer "
                f"cannot start until an operator drains it: {DRAIN_TOOL_HINT}"
            )
            _notify(
                "critical",
                f"Unrecoverable fallback session from block {start}",
                (
                    f"The reprocessing queue holds a fallback session that started at block {start} with {count} "
                    f"blocks. It is {behind} blocks behind the indexer, more than the {MAX_ROLLBACK_BLOCKS}-block "
                    f"rollback bound, so the automatic recovery cannot run. Verify those blocks were re-indexed "
                    f"with Counterparty data (or reindex from {start}) and close the session: {DRAIN_TOOL_HINT}"
                ),
                dedup_key=f"fallback-unrecoverable-{start}",
            )
    return result
