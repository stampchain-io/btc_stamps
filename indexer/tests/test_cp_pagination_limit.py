"""Tests for #756 item 2 — env-driven CP verbose-pagination limit.

The legacy ``limit=25`` workaround for CP v11.0.1's verbose=true bug is now
``CP_VERBOSE_PAGINATION_LIMIT`` (default 100). These tests cover:

- the default value
- env-driven init (run in a subprocess so the running test session's
  already-loaded ``config`` module isn't disturbed — importlib.reload is
  fragile under pytest-xdist parallel workers, manifests as flaky CI)
- the configured value reaches the API call's params dict (regression
  guard against any future re-hardcoding of the limit)

The function-level tests directly patch ``config.CP_VERBOSE_PAGINATION_LIMIT``
instead of reloading the module, which is both safer and stricter (the
function MUST read the live module attribute, not a stale import).
"""

import os
import subprocess
import sys
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

    # In an unconfigured session this is the live value. We don't reload —
    # if some sibling test mutated it, that's a separate concern that
    # subprocess tests below cover authoritatively.
    assert config.CP_VERBOSE_PAGINATION_LIMIT == 100


def _read_config_in_subprocess(env_overrides: dict) -> int:
    """Spawn a child interpreter with the given env overrides applied, import
    ``config``, return the resolved CP_VERBOSE_PAGINATION_LIMIT. Subprocess
    isolation guarantees no cross-test module-state pollution."""
    child_env = os.environ.copy()
    child_env.update(env_overrides)
    code = "import sys; sys.path.insert(0, 'src'); " "import config; " "print(config.CP_VERBOSE_PAGINATION_LIMIT)"
    indexer_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=child_env,
        cwd=indexer_dir,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"child failed: stderr={result.stderr}"
    return int(result.stdout.strip().splitlines()[-1])


def test_env_override():
    """Env var overrides the default."""
    assert _read_config_in_subprocess({"CP_VERBOSE_PAGINATION_LIMIT": "50"}) == 50


def test_invalid_env_falls_back_to_default():
    """Garbage env value falls back to 100, no crash."""
    assert _read_config_in_subprocess({"CP_VERBOSE_PAGINATION_LIMIT": "not-an-int"}) == 100


@pytest.mark.asyncio
async def test_pagination_uses_configured_limit_100():
    """The verbose-safe pagination function must pass the live
    ``config.CP_VERBOSE_PAGINATION_LIMIT`` to every CP API call — guards
    against a regression that re-hardcodes 25.

    Patches via ``fetch_utils.config`` (the exact module object the
    function reads from) rather than the test's separate ``import config``,
    in case any sys.path quirk in CI causes those to resolve to distinct
    module objects.
    """
    from index_core import fetch_utils

    mock_response = {"result": [], "next_cursor": None}

    with patch.object(fetch_utils.config, "CP_VERBOSE_PAGINATION_LIMIT", 100):
        with patch.object(fetch_utils, "fetch_xcp_async", new=AsyncMock(return_value=mock_response)) as mock_fetch:
            await fetch_utils._fetch_block_transactions_verbose_safe_pagination(900000)

    params = mock_fetch.call_args.args[1]
    assert params["limit"] == "100"
    assert params["verbose"] == "true"


@pytest.mark.asyncio
async def test_pagination_passes_lower_limit_when_overridden():
    """If an operator dials limit down (e.g. for a misbehaving upstream),
    the lower value reaches the API call. Patches via ``fetch_utils.config``
    for the same module-identity reasons as the test above."""
    from index_core import fetch_utils

    mock_response = {"result": [], "next_cursor": None}

    with patch.object(fetch_utils.config, "CP_VERBOSE_PAGINATION_LIMIT", 25):
        with patch.object(fetch_utils, "fetch_xcp_async", new=AsyncMock(return_value=mock_response)) as mock_fetch:
            await fetch_utils._fetch_block_transactions_verbose_safe_pagination(900000)

    params = mock_fetch.call_args.args[1]
    assert params["limit"] == "25"
