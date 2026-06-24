"""Tests for #756 item 2 — env-driven CP verbose-pagination limit.

The legacy ``limit=25`` workaround for CP v11.0.1's verbose=true bug is now
``CP_VERBOSE_PAGINATION_LIMIT`` (default 100). These tests cover the env
default + override behavior and that the limit reaches the API call params.
"""

import importlib
import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ["TESTING"] = "1"
os.environ["USE_TEST_DB"] = "1"
os.environ["MOCK_DB"] = "1"
os.environ["RPC_USER"] = "rpc"
os.environ["RPC_PASSWORD"] = "rpc"
os.environ["RPC_IP"] = "127.0.0.1"
os.environ["RPC_PORT"] = "8332"


def test_default_limit_is_100():
    """Without env override, CP_VERBOSE_PAGINATION_LIMIT defaults to 100."""
    import config

    importlib.reload(config)
    assert config.CP_VERBOSE_PAGINATION_LIMIT == 100


def test_env_override():
    """Env var overrides the default."""
    import config

    with patch.dict(os.environ, {"CP_VERBOSE_PAGINATION_LIMIT": "50"}):
        importlib.reload(config)
        assert config.CP_VERBOSE_PAGINATION_LIMIT == 50
    # Reload back to default for test isolation
    importlib.reload(config)


def test_invalid_env_falls_back_to_default():
    """Garbage env value falls back to 100, no crash."""
    import config

    with patch.dict(os.environ, {"CP_VERBOSE_PAGINATION_LIMIT": "not-an-int"}):
        importlib.reload(config)
        assert config.CP_VERBOSE_PAGINATION_LIMIT == 100
    importlib.reload(config)


@pytest.mark.asyncio
async def test_pagination_uses_configured_limit():
    """The verbose-safe pagination function must pass the configured limit
    to every CP API call — guards against a regression that re-hardcodes 25."""
    import config

    # Override before importing the function so it reads the configured value
    with patch.dict(os.environ, {"CP_VERBOSE_PAGINATION_LIMIT": "100"}):
        importlib.reload(config)
        from index_core.fetch_utils import _fetch_block_transactions_verbose_safe_pagination

        # Single-page response (no next_cursor) so we stop after one fetch.
        mock_response = {
            "result": [
                {"tx_hash": "txA", "transaction_type": "send", "block_hash": "block_h"},
            ],
            "next_cursor": None,
        }
        with patch("index_core.fetch_utils.fetch_xcp_async", new=AsyncMock(return_value=mock_response)) as mock_fetch:
            result = await _fetch_block_transactions_verbose_safe_pagination(900000)
            assert result is not None
            # First positional arg is the endpoint; second is the params dict.
            call_args = mock_fetch.call_args
            params = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("params")
            # Allow either positional or kwarg form; locate params dict robustly.
            if params is None:
                # Fall back: scan args/kwargs for a dict containing "limit"
                for candidate in list(call_args.args) + list(call_args.kwargs.values()):
                    if isinstance(candidate, dict) and "limit" in candidate:
                        params = candidate
                        break
            assert params is not None and params.get("limit") == "100"
            assert params.get("verbose") == "true"

    importlib.reload(config)


@pytest.mark.asyncio
async def test_pagination_passes_lower_limit_when_overridden():
    """If an operator dials limit down (e.g. for a misbehaving upstream),
    the lower value reaches the API call."""
    import config

    with patch.dict(os.environ, {"CP_VERBOSE_PAGINATION_LIMIT": "25"}):
        importlib.reload(config)
        from index_core.fetch_utils import _fetch_block_transactions_verbose_safe_pagination

        mock_response = {"result": [], "next_cursor": None}
        with patch("index_core.fetch_utils.fetch_xcp_async", new=AsyncMock(return_value=mock_response)) as mock_fetch:
            await _fetch_block_transactions_verbose_safe_pagination(900000)
            params = mock_fetch.call_args.args[1]
            assert params["limit"] == "25"

    importlib.reload(config)
