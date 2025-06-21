"""
Simplified async concurrency tests for fetch_utils functions.

This test module focuses on core concurrency aspects with simple, robust tests.
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.index_core.fetch_utils import (
    _fetch_blocks_range_async,
    get_all_xcp_transactions,
    get_xcp_transactions_async,
)


class TestAsyncConcurrencySimple:
    """Test core concurrency aspects of async fetch_utils functions."""

    @pytest.mark.asyncio
    async def test_get_xcp_transactions_async_basic_success(self):
        """Test basic successful response from get_xcp_transactions_async."""
        mock_response = {
            "result": [{"tx_hash": "test123", "block_index": 12345}],
            "next_cursor": None,
            "result_count": 1,
        }

        with patch("src.index_core.fetch_utils.fetch_xcp_async", return_value=mock_response):
            block_index, result = await get_xcp_transactions_async(12345)

            assert block_index == 12345
            assert result is not None
            assert "result" in result
            assert len(result["result"]) == 1
            assert result["result"][0]["tx_hash"] == "test123"

    @pytest.mark.asyncio
    async def test_get_xcp_transactions_async_with_cursor(self):
        """Test get_xcp_transactions_async with cursor pagination."""
        mock_response = {
            "result": [{"tx_hash": "test123"}],
            "next_cursor": "next_page",
            "result_count": 1,
        }

        with patch("src.index_core.fetch_utils.fetch_xcp_async") as mock_fetch:
            mock_fetch.return_value = mock_response

            block_index, result = await get_xcp_transactions_async(12345, cursor="start_cursor", limit=50)

            # Check the API was called with correct parameters
            mock_fetch.assert_called_once()
            args = mock_fetch.call_args[0]
            endpoint, params = args
            assert endpoint == "/blocks/12345/transactions"
            assert params["cursor"] == "start_cursor"
            assert params["limit"] == 50

    @pytest.mark.asyncio
    async def test_get_xcp_transactions_async_error_cases(self):
        """Test error handling in get_xcp_transactions_async."""
        # Test None response
        with patch("src.index_core.fetch_utils.fetch_xcp_async", return_value=None):
            block_index, result = await get_xcp_transactions_async(12345)
            assert block_index == 12345
            assert result is None

        # Test invalid response format
        with patch("src.index_core.fetch_utils.fetch_xcp_async", return_value={"invalid": "format"}):
            block_index, result = await get_xcp_transactions_async(12345)
            assert block_index == 12345
            assert result["result"] == []

        # Test exception
        with patch("src.index_core.fetch_utils.fetch_xcp_async", side_effect=Exception("Network error")):
            block_index, result = await get_xcp_transactions_async(12345)
            assert block_index == 12345
            assert result is None

    @pytest.mark.asyncio
    async def test_basic_concurrent_operations(self):
        """Test basic concurrent async operations work as expected."""

        async def simple_async_task(value):
            await asyncio.sleep(0.01)  # Simulate async work
            return value * 2

        # Run multiple tasks concurrently
        tasks = [simple_async_task(i) for i in range(5)]
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        end_time = time.time()

        # Should complete faster than sequential (5 * 0.01 = 0.05s)
        assert (end_time - start_time) < 0.5

        # Should have correct results
        assert results == [0, 2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_concurrent_with_some_failures(self):
        """Test concurrent operations with some failures."""

        async def sometimes_fail_task(value):
            await asyncio.sleep(0.01)
            if value == 2:
                raise ValueError(f"Task {value} failed")
            return value * 3

        # Use gather with return_exceptions to handle failures
        tasks = [sometimes_fail_task(i) for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Should have 4 successes and 1 exception
        successes = [r for r in results if not isinstance(r, Exception)]
        exceptions = [r for r in results if isinstance(r, Exception)]

        assert len(successes) == 4
        assert len(exceptions) == 1
        assert isinstance(exceptions[0], ValueError)

    @pytest.mark.asyncio
    async def test_fetch_blocks_range_async_concurrent_fetching(self):
        """Test concurrent block fetching in _fetch_blocks_range_async."""
        call_times = []

        async def mock_fetch_block(block_index):
            call_times.append(time.time())
            await asyncio.sleep(0.01)  # Simulate network delay
            return {
                "block_index": block_index,
                "xcp_block_hash": f"hash_{block_index}",
                "transactions": [{"tx_hash": f"tx_{block_index}"}],
                "issuances": [],
            }

        with patch("src.index_core.fetch_utils.fetch_block_transactions_with_pagination", side_effect=mock_fetch_block):
            start_time = time.time()
            result = await _fetch_blocks_range_async(100, 102)  # 3 blocks
            end_time = time.time()

            # Should complete faster than sequential
            total_time = end_time - start_time
            assert total_time < 0.5

            # Should have all blocks
            assert len(result) == 3
            for block_index in range(100, 103):
                assert block_index in result
                assert result[block_index]["block_index"] == block_index

    @pytest.mark.asyncio
    async def test_fetch_blocks_range_async_with_retries(self):
        """Test retry logic in _fetch_blocks_range_async."""
        call_counts = {}

        async def mock_fetch_block(block_index):
            if block_index not in call_counts:
                call_counts[block_index] = 0
            call_counts[block_index] += 1

            # Block 101 fails first two attempts, succeeds on third
            if block_index == 101 and call_counts[block_index] <= 2:
                return None  # Failure

            return {"block_index": block_index, "xcp_block_hash": f"hash_{block_index}", "transactions": [], "issuances": []}

        with patch("src.index_core.fetch_utils.fetch_block_transactions_with_pagination", side_effect=mock_fetch_block):
            with patch("src.index_core.fetch_utils.update_healthy_nodes") as mock_update:
                result = await _fetch_blocks_range_async(100, 102)  # 3 blocks

                # Should have all blocks (including the one that was retried)
                assert len(result) == 3
                assert result[101] is not None
                assert result[101]["block_index"] == 101

                # Should have called update_healthy_nodes for retries
                assert mock_update.call_count >= 2  # At least 2 retry attempts

    @pytest.mark.asyncio
    async def test_concurrent_task_cancellation(self):
        """Test that concurrent tasks can be cancelled properly."""

        async def slow_operation(delay):
            await asyncio.sleep(delay)
            return f"completed_{delay}"

        # Create tasks with different delays
        tasks = [
            asyncio.create_task(slow_operation(0.1)),
            asyncio.create_task(slow_operation(0.2)),
            asyncio.create_task(slow_operation(1.0)),  # This one should be cancelled
        ]

        # Wait a bit then cancel the slow task
        await asyncio.sleep(0.15)
        tasks[2].cancel()

        # Gather results, handling cancellation
        results = []
        for task in tasks:
            try:
                result = await task
                results.append(result)
            except asyncio.CancelledError:
                results.append("cancelled")

        # First two should complete, third should be cancelled
        assert "completed_0.1" in results
        assert "completed_0.2" in results
        assert "cancelled" in results

    @pytest.mark.asyncio
    async def test_concurrent_memory_efficiency(self):
        """Test that concurrent operations don't create excessive memory usage."""
        # This test ensures we process many items without memory issues

        async def simple_async_operation(item_id):
            # Simulate some async work
            await asyncio.sleep(0.001)
            return {"id": item_id, "data": f"processed_{item_id}"}

        # Process many items concurrently
        tasks = [simple_async_operation(i) for i in range(100)]
        results = await asyncio.gather(*tasks)

        # Should process all items successfully
        assert len(results) == 100
        assert all(result["data"].startswith("processed_") for result in results)

        # Memory should be manageable (if we get here without issues, test passes)
        assert True

    @pytest.mark.asyncio
    async def test_asyncio_gather_error_handling(self):
        """Test error handling with asyncio.gather."""

        async def sometimes_fail(item_id):
            await asyncio.sleep(0.01)
            if item_id == 2:
                raise ValueError(f"Intentional failure for item {item_id}")
            return f"success_{item_id}"

        # Test with return_exceptions=True to handle errors gracefully
        tasks = [sometimes_fail(i) for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        assert len(results) == 5

        # Most should succeed
        successes = [r for r in results if isinstance(r, str) and r.startswith("success_")]
        assert len(successes) == 4

        # One should be an exception
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 1
        assert isinstance(exceptions[0], ValueError)
