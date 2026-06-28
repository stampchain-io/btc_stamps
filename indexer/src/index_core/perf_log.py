"""
Lightweight, failure-isolated structured per-block performance logging.

This module is consensus-neutral: it only serializes timing/counter data and
appends it to a JSONL file. It must never affect block processing, so the
single public entry point swallows all errors (logging them at DEBUG level).

Activation is controlled by the ``PERF_LOG`` / ``PERF_LOG_PATH`` config flags;
callers are expected to guard invocations behind ``config.PERF_LOG`` so there
is zero overhead when the feature is disabled.
"""

import json
import logging

logger = logging.getLogger(__name__)


def record_block_perf(path, fields):
    """Append one JSON object (a single JSONL line) describing a block's timings.

    Args:
        path: Destination JSONL file path (appended to, created if missing).
        fields: Mapping of perf fields to serialize for this block.

    Any error (serialization or I/O) is logged at DEBUG and swallowed so that
    perf logging can never disrupt block processing.
    """
    try:
        line = json.dumps(fields, separators=(",", ":"), sort_keys=False)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception as e:  # noqa: BLE001 - perf logging must never raise
        logger.debug(f"perf log write failed (ignored): {e}")
