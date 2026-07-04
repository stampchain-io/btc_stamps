"""
Tests for the active CP-readiness re-poll helper (issue #821).

At chain tip a transient "CP not ready" used to defer a block until the *next*
ZMQ notification arrived, costing a whole block interval (~14 min observed).
``wait_for_cp_block_ready_with_repoll`` instead re-polls the SAME pending block
on a short, bounded cadence so the indexer proceeds as soon as CP catches up.

These tests verify (with all sleeps mocked, deterministically):
1. transient not-ready -> ready re-polls and proceeds WITHOUT a new ZMQ
   notification (the core regression);
2. the overall re-poll bound is respected (gives up, does not spin forever);
3. the readiness gate is NOT loosened: ``db_caught_up=False`` still blocks;
4. config knobs are resolved at call-time (env/test overrides honored).
"""

from unittest.mock import patch

import pytest

import config
from src.index_core.fetch_utils import (
    wait_for_cp_block_processed,
    wait_for_cp_block_ready_with_repoll,
)


@pytest.mark.unit
class TestCPReadinessRepoll:
    """Bounded re-poll loop around wait_for_cp_block_processed."""

    def test_transient_not_ready_then_ready_proceeds_without_new_notification(self):
        """Core regression: a transient miss re-polls the SAME block and proceeds.

        We do NOT wait for a new ZMQ notification; the helper itself retries.
        """
        with patch(
            "src.index_core.fetch_utils.wait_for_cp_block_processed",
            side_effect=[False, True],
        ) as mock_wait:
            with patch("time.sleep") as mock_sleep:
                result = wait_for_cp_block_ready_with_repoll(850000, max_wait=60.0, repoll_interval=5.0, repoll_max=300.0)

        assert result is True
        assert mock_wait.call_count == 2  # re-polled the same pending block once
        assert mock_sleep.call_count == 1  # slept once between attempts

    def test_immediate_ready_does_not_sleep(self):
        """If CP is already ready, return True without any re-poll sleep."""
        with patch(
            "src.index_core.fetch_utils.wait_for_cp_block_processed",
            return_value=True,
        ) as mock_wait:
            with patch("time.sleep") as mock_sleep:
                result = wait_for_cp_block_ready_with_repoll(850000, max_wait=60.0, repoll_interval=5.0, repoll_max=300.0)

        assert result is True
        assert mock_wait.call_count == 1
        assert mock_sleep.call_count == 0

    def test_overall_bound_respected_gives_up(self):
        """A genuinely stuck CP surfaces (returns False) after the bound, no infinite spin."""
        clock = {"t": 1000.0}

        def fake_time():
            return clock["t"]

        def fake_sleep(seconds):
            clock["t"] += seconds

        with patch(
            "src.index_core.fetch_utils.wait_for_cp_block_processed",
            return_value=False,
        ) as mock_wait:
            with patch("time.sleep", side_effect=fake_sleep):
                with patch("time.time", side_effect=fake_time):
                    result = wait_for_cp_block_ready_with_repoll(850000, max_wait=10.0, repoll_interval=5.0, repoll_max=15.0)

        assert result is False
        # Bounded: start t=1000; attempts at elapsed 0,5,10 sleep each, attempt at
        # elapsed 15 hits the bound and returns. 4 attempts, 3 sleeps.
        assert mock_wait.call_count == 4
        assert clock["t"] == 1015.0

    def test_db_caught_up_false_still_blocks(self):
        """The gate is NOT loosened: db_caught_up=False must keep blocking.

        Exercises the real wait_for_cp_block_processed (height ok, db_caught_up
        False) and confirms it times out to False, then the re-poll helper also
        surfaces False after its bound.
        """
        not_caught_up = {"last_block": 850000, "db_caught_up": False, "version": "10.1.0"}
        nodes = [{"url": "http://test-node:4000"}]

        clock = {"t": 1000.0}

        def fake_time():
            return clock["t"]

        def fake_sleep(seconds):
            clock["t"] += seconds

        with patch("src.index_core.fetch_utils.get_healthy_nodes", return_value=nodes):
            with patch(
                "src.index_core.fetch_utils.fetch_node_version_v2",
                return_value=(True, not_caught_up),
            ):
                with patch("time.sleep", side_effect=fake_sleep):
                    with patch("time.time", side_effect=fake_time):
                        # Direct gate check: height is sufficient but db not caught up -> False.
                        direct = wait_for_cp_block_processed(850000, max_wait=4.0, check_interval=2.0)
                        assert direct is False

                        # Reset clock for the re-poll wrapper and confirm it also surfaces False.
                        clock["t"] = 1000.0
                        wrapped = wait_for_cp_block_ready_with_repoll(
                            850000, max_wait=4.0, repoll_interval=2.0, repoll_max=8.0
                        )
                        assert wrapped is False

    def test_config_resolved_at_call_time(self, monkeypatch):
        """When args are omitted, the helper reads CP_READY_* from config at call-time."""
        monkeypatch.setattr(config, "CP_READY_MAX_WAIT", 42.0, raising=False)
        monkeypatch.setattr(config, "CP_READY_REPOLL_INTERVAL", 3.0, raising=False)
        monkeypatch.setattr(config, "CP_READY_REPOLL_MAX", 99.0, raising=False)

        with patch(
            "src.index_core.fetch_utils.wait_for_cp_block_processed",
            return_value=True,
        ) as mock_wait:
            with patch("time.sleep"):
                result = wait_for_cp_block_ready_with_repoll(850000)

        assert result is True
        # Inner call uses the configured per-attempt window and the modest interval.
        mock_wait.assert_called_once_with(850000, max_wait=42.0, check_interval=3.0)
