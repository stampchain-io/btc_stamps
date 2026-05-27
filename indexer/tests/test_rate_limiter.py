"""Tests for the proactive CP rate limiter in fetch_utils."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from index_core import fetch_utils


@pytest.fixture(autouse=True)
def _clean_rate_limiters():
    """Reset module-level rate-limiter registry between tests."""
    fetch_utils._rate_limiters.clear()
    yield
    fetch_utils._rate_limiters.clear()


def test_is_public_cp_endpoint_classification():
    assert fetch_utils._is_public_cp_endpoint("https://api.counterparty.io:4000/v2/blocks") is True
    assert fetch_utils._is_public_cp_endpoint("HTTPS://API.COUNTERPARTY.IO/x") is True
    assert fetch_utils._is_public_cp_endpoint("http://127.0.0.1:4000/v2/blocks") is False
    assert fetch_utils._is_public_cp_endpoint("http://10.0.0.5:4000/x") is False


def test_get_rate_limiter_returns_per_class_singletons():
    pub1 = fetch_utils.get_rate_limiter_for_url("https://api.counterparty.io/a")
    pub2 = fetch_utils.get_rate_limiter_for_url("https://api.counterparty.io/b")
    loc1 = fetch_utils.get_rate_limiter_for_url("http://127.0.0.1:4000/a")
    loc2 = fetch_utils.get_rate_limiter_for_url("http://192.168.1.5:4000/x")
    assert pub1 is pub2
    assert loc1 is loc2
    assert pub1 is not loc1


def test_rate_limiter_enforces_min_interval_sync():
    rl = fetch_utils.RateLimiter(calls_per_second=10.0)  # 100ms min interval
    t0 = time.time()
    rl.acquire()
    rl.acquire()
    rl.acquire()
    elapsed = time.time() - t0
    # 3 calls × 100ms = ~200ms (first is free, then 2 × 100ms)
    assert elapsed >= 0.18, f"expected >=0.18s, got {elapsed:.3f}s"


def test_rate_limiter_zero_wait_when_idle():
    rl = fetch_utils.RateLimiter(calls_per_second=10.0)
    rl.acquire()
    time.sleep(0.2)  # exceed the min interval
    wait = rl.acquire()
    assert wait == 0.0


@pytest.mark.asyncio
async def test_rate_limiter_async_enforces_interval():
    rl = fetch_utils.RateLimiter(calls_per_second=10.0)
    t0 = time.time()
    await rl.acquire_async()
    await rl.acquire_async()
    await rl.acquire_async()
    elapsed = time.time() - t0
    assert elapsed >= 0.18, f"expected >=0.18s, got {elapsed:.3f}s"


def test_parse_retry_after_seconds():
    assert fetch_utils._parse_retry_after("30") == 30.0
    assert fetch_utils._parse_retry_after("0") == 0.0
    assert fetch_utils._parse_retry_after(45) == 45.0


def test_parse_retry_after_invalid_returns_default():
    assert fetch_utils._parse_retry_after(None) == 60.0
    assert fetch_utils._parse_retry_after("") == 60.0
    assert fetch_utils._parse_retry_after("garbage") == 60.0


def test_parse_retry_after_http_date_format():
    """Accepts HTTP-date format and returns a positive duration."""
    # A date 30 minutes in the future. We can't bind to an exact second
    # but we can verify it's parsed and >0.
    import datetime
    from email.utils import format_datetime

    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=120)
    header = format_datetime(future)
    delta = fetch_utils._parse_retry_after(header)
    assert 100 < delta < 140, f"expected ~120s, got {delta}"


def test_rate_limiter_initialized_at_configured_rate(monkeypatch):
    """Public-class limiter uses CP_PUBLIC_API_LIMIT, local-class uses CP_LOCAL_NODE_LIMIT."""
    # fetch_utils imports the top-level `config` module (src/config.py),
    # not index_core.config. Patch that one.
    import config as top_config

    monkeypatch.setattr(top_config, "CP_PUBLIC_API_LIMIT", 3.0)
    monkeypatch.setattr(top_config, "CP_LOCAL_NODE_LIMIT", 25.0)
    fetch_utils._rate_limiters.clear()  # force re-init

    pub = fetch_utils.get_rate_limiter_for_url("https://api.counterparty.io/x")
    loc = fetch_utils.get_rate_limiter_for_url("http://127.0.0.1/x")
    assert pub.calls_per_second == 3.0
    assert loc.calls_per_second == 25.0
