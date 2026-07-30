"""
Tests for the async (off-critical-path) SRC-20 ledger-hash validation dispatch.

Issue #877: the per-block SRC-20 ledger-hash cross-check against stampscan is a
synchronous HTTPS GET made inside each SRC-20-bearing block's DB transaction.
``dispatch_src20_ledger_validation`` moves that check to the already-running
background validator when ``config.SRC20_LEDGER_VALIDATION_ASYNC`` is enabled
(and the background validator is on), keeping the inline path byte-for-byte
identical when the flag is off.

These tests assert the routing decision, the fall-back safety (async requested
but background validator disabled -> stay inline), the enqueue wrapper, and that
the inline-mismatch alert is preserved. They are consensus-neutral: the check is
observational either way (on a real mismatch it only alerts and keeps indexing).
"""

import unittest
from unittest.mock import patch

from index_core.blocks import (
    _alert_src20_ledger_mismatch,
    dispatch_src20_ledger_validation,
)
from index_core.src20 import enqueue_src20_ledger_validation


class TestDispatchSrc20LedgerValidation(unittest.TestCase):
    """Routing between the inline stampscan check and the background validator."""

    BLOCK = 800000
    HASH = "deadbeef"
    SRC20_STR = "TEST,addr1,100.5;TEST,addr2,200.25"

    def test_inline_when_async_flag_off(self):
        """Flag off -> validate inline (current behavior); never enqueue."""
        with patch("config.SRC20_LEDGER_VALIDATION_ASYNC", False), patch(
            "config.ENABLE_SRC20_BACKGROUND_VALIDATION", True
        ), patch("index_core.blocks.validate_src20_ledger_hash", return_value=True) as mock_validate, patch(
            "index_core.blocks.enqueue_src20_ledger_validation"
        ) as mock_enqueue:
            dispatch_src20_ledger_validation(self.BLOCK, self.HASH, self.SRC20_STR)

        mock_validate.assert_called_once_with(self.BLOCK, self.HASH, self.SRC20_STR)
        mock_enqueue.assert_not_called()

    def test_defer_when_async_and_background_enabled(self):
        """Flag on + background validator on -> enqueue; no inline HTTP call."""
        with patch("config.SRC20_LEDGER_VALIDATION_ASYNC", True), patch(
            "config.ENABLE_SRC20_BACKGROUND_VALIDATION", True
        ), patch("index_core.blocks.validate_src20_ledger_hash") as mock_validate, patch(
            "index_core.blocks.enqueue_src20_ledger_validation"
        ) as mock_enqueue:
            dispatch_src20_ledger_validation(self.BLOCK, self.HASH, self.SRC20_STR)

        mock_enqueue.assert_called_once_with(self.BLOCK, self.HASH, self.SRC20_STR)
        mock_validate.assert_not_called()

    def test_inline_when_async_on_but_background_disabled(self):
        """Safety fall-back: async requested but background validator off -> stay
        inline, so a block is never enqueued into a validator that will never run.
        """
        with patch("config.SRC20_LEDGER_VALIDATION_ASYNC", True), patch(
            "config.ENABLE_SRC20_BACKGROUND_VALIDATION", False
        ), patch("index_core.blocks.validate_src20_ledger_hash", return_value=True) as mock_validate, patch(
            "index_core.blocks.enqueue_src20_ledger_validation"
        ) as mock_enqueue:
            dispatch_src20_ledger_validation(self.BLOCK, self.HASH, self.SRC20_STR)

        mock_validate.assert_called_once_with(self.BLOCK, self.HASH, self.SRC20_STR)
        mock_enqueue.assert_not_called()

    def test_inline_mismatch_triggers_alert(self):
        """Inline path: a real mismatch (validate -> False) fires the ops alert."""
        with patch("config.SRC20_LEDGER_VALIDATION_ASYNC", False), patch(
            "config.ENABLE_SRC20_BACKGROUND_VALIDATION", True
        ), patch("index_core.blocks.validate_src20_ledger_hash", return_value=False), patch(
            "index_core.blocks._alert_src20_ledger_mismatch"
        ) as mock_alert:
            dispatch_src20_ledger_validation(self.BLOCK, self.HASH, self.SRC20_STR)

        mock_alert.assert_called_once_with(self.BLOCK)

    def test_inline_match_does_not_alert(self):
        """Inline path: a match (validate -> True) does not alert."""
        with patch("config.SRC20_LEDGER_VALIDATION_ASYNC", False), patch(
            "config.ENABLE_SRC20_BACKGROUND_VALIDATION", True
        ), patch("index_core.blocks.validate_src20_ledger_hash", return_value=True), patch(
            "index_core.blocks._alert_src20_ledger_mismatch"
        ) as mock_alert:
            dispatch_src20_ledger_validation(self.BLOCK, self.HASH, self.SRC20_STR)

        mock_alert.assert_not_called()

    def test_async_path_does_not_alert_inline(self):
        """Async path never runs the inline mismatch alert (that is the background
        validator's job)."""
        with patch("config.SRC20_LEDGER_VALIDATION_ASYNC", True), patch(
            "config.ENABLE_SRC20_BACKGROUND_VALIDATION", True
        ), patch("index_core.blocks.enqueue_src20_ledger_validation"), patch(
            "index_core.blocks._alert_src20_ledger_mismatch"
        ) as mock_alert:
            dispatch_src20_ledger_validation(self.BLOCK, self.HASH, self.SRC20_STR)

        mock_alert.assert_not_called()


class TestEnqueueSrc20LedgerValidation(unittest.TestCase):
    """The public enqueue wrapper used by the async path."""

    def test_enqueue_adds_to_queue(self):
        """Delegates to ValidationQueueManager.add_to_queue with (block, hash, str)."""
        with patch("index_core.validation_queue.ValidationQueueManager") as mock_mgr:
            enqueue_src20_ledger_validation(800001, "hash1", "TEST,addr1,1")
            mock_mgr.get_instance.return_value.add_to_queue.assert_called_once_with(800001, "hash1", "TEST,addr1,1")

    def test_enqueue_never_raises_on_queue_failure(self):
        """A queue failure must be swallowed -- the indexer loop must keep moving."""
        with patch("index_core.validation_queue.ValidationQueueManager") as mock_mgr:
            mock_mgr.get_instance.return_value.add_to_queue.side_effect = RuntimeError("queue down")
            # Must not raise.
            enqueue_src20_ledger_validation(800002, "hash2", "TEST,addr1,1")


class TestAlertSrc20LedgerMismatch(unittest.TestCase):
    """The inline mismatch alert helper (behavior preserved from the pre-refactor
    finalize_block block)."""

    def test_alert_sends_critical_with_dedup_key(self):
        with patch("index_core.ops_alerter.notify") as mock_notify:
            _alert_src20_ledger_mismatch(800003)

        mock_notify.assert_called_once()
        args, kwargs = mock_notify.call_args
        assert args[0] == "critical"
        assert "800003" in args[1]
        assert kwargs.get("dedup_key") == "src20-mismatch-800003"

    def test_alert_never_raises_when_notify_fails(self):
        """Alerting failure must not crash the main loop."""
        with patch("index_core.ops_alerter.notify", side_effect=RuntimeError("sns down")):
            # Must not raise.
            _alert_src20_ledger_mismatch(800004)


if __name__ == "__main__":
    unittest.main()
