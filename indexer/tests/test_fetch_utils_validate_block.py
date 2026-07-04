"""Tests for _validate_block_data_completeness empty-block guard.

Covers the regression where a transient 0-transactions response from CP was
accepted as a legitimate empty block, silently dropping any issuances/transfers
in that block (see incident with A15716034302284605000 in block 954140).
"""

from unittest.mock import AsyncMock, patch

import pytest

from index_core.fetch_utils import _validate_block_data_completeness


@pytest.mark.asyncio
async def test_empty_block_accepted_when_probe_confirms_zero():
    """Block truly empty (CP says 0 too) — accept."""
    block_data = {"transactions": []}
    with patch(
        "index_core.fetch_utils.fetch_xcp_async",
        new=AsyncMock(return_value={"result": [], "result_count": 0}),
    ):
        assert await _validate_block_data_completeness(900000, block_data) is True


@pytest.mark.asyncio
async def test_empty_block_rejected_when_probe_says_nonzero():
    """Fetcher returned 0 but CP says there are transactions — reject so caller retries."""
    block_data = {"transactions": []}
    with patch(
        "index_core.fetch_utils.fetch_xcp_async",
        new=AsyncMock(return_value={"result": [], "result_count": 7}),
    ):
        assert await _validate_block_data_completeness(900000, block_data) is False


@pytest.mark.asyncio
async def test_empty_block_accepted_when_probe_fails():
    """Probe network failure — fall back to current behavior (accept) so the
    validator isn't a new outage vector."""
    block_data = {"transactions": []}
    with patch(
        "index_core.fetch_utils.fetch_xcp_async",
        new=AsyncMock(side_effect=Exception("simulated network failure")),
    ):
        assert await _validate_block_data_completeness(900000, block_data) is True


@pytest.mark.asyncio
async def test_empty_block_accepted_when_probe_has_no_count_field():
    """Probe succeeds but response is malformed (no result_count) — accept."""
    block_data = {"transactions": []}
    with patch(
        "index_core.fetch_utils.fetch_xcp_async",
        new=AsyncMock(return_value={"result": []}),
    ):
        assert await _validate_block_data_completeness(900000, block_data) is True


@pytest.mark.asyncio
async def test_nonempty_block_skips_probe():
    """When the fetcher returned transactions, the count probe is never reached."""
    block_data = {"transactions": [{"tx_hash": "deadbeef" * 8}]}
    mock_fetch = AsyncMock()
    with patch("index_core.fetch_utils.fetch_xcp_async", new=mock_fetch):
        assert await _validate_block_data_completeness(900000, block_data) is True
    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_missing_transactions_field_rejected():
    """Pre-existing behavior preserved: missing key fails fast."""
    assert await _validate_block_data_completeness(900000, {}) is False
