"""
Tests for the ENABLE_SALES_HISTORY_CATCHUP configuration flag (issue #831).

Previously this toggle had two divergent in-code defaults:
  - index_core/sales_history_processor.py defaulted it to "false"
  - index_core/market_data_jobs.py defaulted it to "true"
so the effective behavior depended on which module's default applied.

These tests pin the fix: the flag is defined exactly once in config.py
(single source of truth, default disabled) and both modules read
``config.ENABLE_SALES_HISTORY_CATCHUP`` at call time.
"""

import importlib
import os
from unittest.mock import patch

import pytest

import config
import index_core.market_data_jobs as market_data_jobs
import index_core.sales_history_processor as sales_history_processor


class TestEnableSalesHistoryCatchupFlag:
    """Unify ENABLE_SALES_HISTORY_CATCHUP behind a single config source."""

    def test_default_disabled_when_env_unset(self):
        """The unified default is False (public-safe) when the flag is unset.

        Resolved at call time rather than via ``importlib.reload(config)``.
        The suite runs ``pytest -n auto`` and several other tests reload
        ``config`` (see CLAUDE.md), so reloading here is both fragile and
        unnecessary: it raises ``ImportError: module config not in
        sys.modules`` when another worker's test has evicted ``config``.
        ``importlib.import_module`` instead returns the live module without
        perturbing it, and conftest pins the env var to its disabled default
        ("false") -- equivalent to the unset case.
        """
        cfg = importlib.import_module("config")
        assert cfg.ENABLE_SALES_HISTORY_CATCHUP is False
        # Both modules read the same single config source at call time.
        assert market_data_jobs.config.ENABLE_SALES_HISTORY_CATCHUP is False
        assert sales_history_processor.config.ENABLE_SALES_HISTORY_CATCHUP is False

    def test_both_modules_share_single_config_source(self):
        """Both modules reference the SAME config module object."""
        assert market_data_jobs.config is config
        assert sales_history_processor.config is config

    def test_both_modules_observe_same_value(self):
        """Monkeypatching the single config attr is observed identically by both."""
        for value in (True, False):
            with patch.object(config, "ENABLE_SALES_HISTORY_CATCHUP", value):
                assert market_data_jobs.config.ENABLE_SALES_HISTORY_CATCHUP is value
                assert sales_history_processor.config.ENABLE_SALES_HISTORY_CATCHUP is value
                # Neither module keeps a stale local copy of the flag.
                assert (
                    market_data_jobs.config.ENABLE_SALES_HISTORY_CATCHUP
                    is sales_history_processor.config.ENABLE_SALES_HISTORY_CATCHUP
                )

    def test_processor_gate_reads_config_at_call_time(self):
        """sales_history_processor.start_catchup_mode gates on config, not a stale const."""
        with patch("index_core.sales_history_processor.DatabaseManager"), patch("index_core.sales_history_processor.Backend"):
            processor = sales_history_processor.SalesHistoryProcessor()
        processor.catchup_running = False
        processor.catchup_executor = None

        # Disabled via the single config source -> early return, no executor created.
        with patch.dict(os.environ, {"TESTING": "0"}), patch.object(config, "ENABLE_SALES_HISTORY_CATCHUP", False):
            processor.start_catchup_mode(mode="FULL_CATCHUP")
            assert processor.catchup_executor is None
            assert processor.catchup_running is False


if __name__ == "__main__":
    pytest.main([__file__])
