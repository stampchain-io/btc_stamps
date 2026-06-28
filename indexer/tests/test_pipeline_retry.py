#!/usr/bin/env python
"""
Unit tests for the CPBlocksPipeline retry-storm fix (issue #838).

These tests exercise the retry-selection / pruning logic in isolation (no DB, no
network, no worker thread). They assert that the prefetch pipeline:

  (a) DROPS a failed block once the main parser has advanced past it
      (instead of endlessly retrying a block that is no longer needed);
  (b) does NOT re-queue a permanently-failed (dead) block for another retry cycle;
  (c) logs a permanent failure exactly ONCE, not once per retry cycle.

The pipeline is constructed with fallback_mode=False so it never touches the
SQLite ReprocessingQueue or any external node.
"""

import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

current_dir = Path(__file__).parent.parent.absolute()
src_path = current_dir / "src"
sys.path.insert(0, str(src_path))

from index_core.pipeline_utils import CPBlocksPipeline  # noqa: E402

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")


class TestPipelineRetryStorm(unittest.TestCase):
    """Validate the issue #838 retry-storm fixes."""

    def setUp(self):
        # fallback_mode=False -> no state_manager / DB; pure in-memory object.
        self.pipeline = CPBlocksPipeline(fallback_mode=False)

    def tearDown(self):
        # No worker thread was started; just release the executor.
        try:
            self.pipeline.fetch_executor.shutdown(wait=False)
        except Exception:
            pass

    def test_block_behind_frontier_is_dropped_not_retried(self):
        """(a) A failed block below the parser frontier is dropped, never retried."""
        processor_position = 1000
        fetch_end_block = 1050
        # 995 is BEHIND the frontier (already processed by the main loop);
        # 1010 is ahead and still a legitimate retry candidate.
        self.pipeline.failed_fetch_blocks = {995: 1, 1010: 1}

        retry = self.pipeline._prune_and_select_failed_blocks(
            processor_position, fetch_end_block, blocks_already_present=set()
        )

        # The passed block is evicted entirely and NOT scheduled for retry.
        self.assertNotIn(995, retry)
        self.assertNotIn(995, self.pipeline.failed_fetch_blocks)
        # The still-needed block ahead of the frontier IS retried (happy path intact).
        self.assertIn(1010, retry)

    def test_permanently_failed_block_not_requeued(self):
        """(b) A block that exhausted retries is dropped and never retried again."""
        processor_position = 1000
        fetch_end_block = 1050
        # 1005 has reached max_fetch_retries -> should become "dead".
        self.pipeline.failed_fetch_blocks = {1005: self.pipeline.max_fetch_retries}

        retry = self.pipeline._prune_and_select_failed_blocks(
            processor_position, fetch_end_block, blocks_already_present=set()
        )

        self.assertNotIn(1005, retry)
        self.assertIn(1005, self.pipeline.dead_blocks)
        self.assertNotIn(1005, self.pipeline.failed_fetch_blocks)

        # Simulate a stray re-add of the dead block on a later cycle: it must be
        # evicted immediately and never scheduled for retry.
        self.pipeline.failed_fetch_blocks = {1005: 1}
        retry2 = self.pipeline._prune_and_select_failed_blocks(
            processor_position, fetch_end_block, blocks_already_present=set()
        )
        self.assertNotIn(1005, retry2)
        self.assertNotIn(1005, self.pipeline.failed_fetch_blocks)

    def test_permanent_failure_logged_once(self):
        """(c) The permanent-failure ERROR is emitted once, not per retry cycle."""
        processor_position = 1000
        fetch_end_block = 1050

        with patch("index_core.pipeline_utils.logger") as mock_logger:
            # First cycle: block hits max retries -> one ERROR.
            self.pipeline.failed_fetch_blocks = {1005: self.pipeline.max_fetch_retries}
            self.pipeline._prune_and_select_failed_blocks(processor_position, fetch_end_block, blocks_already_present=set())

            # Subsequent cycles with the same block re-appearing: no further ERRORs,
            # because it is already in dead_blocks and evicted before logging.
            for _ in range(5):
                self.pipeline.failed_fetch_blocks = {1005: self.pipeline.max_fetch_retries}
                self.pipeline._prune_and_select_failed_blocks(
                    processor_position, fetch_end_block, blocks_already_present=set()
                )

            permanent_failure_errors = [call for call in mock_logger.error.call_args_list if "permanently failed" in str(call)]
            self.assertEqual(
                len(permanent_failure_errors),
                1,
                f"Expected exactly one permanent-failure ERROR, got {len(permanent_failure_errors)}",
            )

    def test_mark_block_dead_is_idempotent(self):
        """_mark_block_dead logs once and is a no-op on repeat calls."""
        with patch("index_core.pipeline_utils.logger") as mock_logger:
            self.pipeline._mark_block_dead(2000, 3)
            self.pipeline._mark_block_dead(2000, 3)
            self.pipeline._mark_block_dead(2000, 4)
            self.assertIn(2000, self.pipeline.dead_blocks)
            self.assertEqual(mock_logger.error.call_count, 1)


if __name__ == "__main__":
    unittest.main()
