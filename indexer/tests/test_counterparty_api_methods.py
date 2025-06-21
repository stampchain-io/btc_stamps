"""
Test Counterparty API methods to ensure data consistency.

This test module validates that both the workaround (2-step) and original (verbose=true)
methods produce identical data structures. This is crucial for ensuring we can safely
switch between methods when the upstream API bug is fixed.
"""

import asyncio
import os
from typing import Dict, Any, List
from unittest.mock import patch, AsyncMock

import pytest

from src.index_core.fetch_utils import (
    _fetch_block_transactions_workaround,
    _fetch_block_transactions_original,
    fetch_block_transactions_with_pagination,
)


class TestCounterpartyAPIMethods:
    """Test both Counterparty API methods for data consistency."""

    @pytest.fixture
    def mock_api_responses(self):
        """Mock API responses for testing."""
        # Mock transaction response (verbose=false)
        transactions_response = {
            "result": [
                {
                    "tx_hash": "a28a6453d4265cd01e2a7b31f8502c1b58e8b3251bc45f4d96f5c4a10de088d8",
                    "block_index": 784320,
                    "block_hash": "0000000000000000000242de64b82e56ca039b1e192b8bfa067b1fc0fb640d86",
                    "block_time": 1679350492,
                    "source": "bc1qm4keajcuk5u5qdvpx5kaglghahxp8v4q96mdmc",
                    "destination": None,
                    "btc_amount": 0,
                    "fee": 10000,
                    "data": "hexdata",
                    "transaction_type": "issuance",
                    "supported": True,
                },
                {
                    "tx_hash": "35827166d851ddc308e1e12a9492ae6656c14c26b6b5f8135c96e1db978c76f1",
                    "block_index": 784320,
                    "block_hash": "0000000000000000000242de64b82e56ca039b1e192b8bfa067b1fc0fb640d86",
                    "block_time": 1679350492,
                    "source": "bc1qtest123",
                    "destination": None,
                    "btc_amount": 0,
                    "fee": 10000,
                    "data": "hexdata2",
                    "transaction_type": "send",
                    "supported": True,
                },
            ],
            "next_cursor": None,
            "result_count": 2,
        }

        # Mock events response
        events_response = {
            "result": [
                {
                    "event_index": 2304003,
                    "event": "ASSET_ISSUANCE",
                    "params": {
                        "asset": "A1937300887712877300",
                        "asset_longname": None,
                        "quantity": 100,
                        "divisible": False,
                        "source": "bc1qm4keajcuk5u5qdvpx5kaglghahxp8v4q96mdmc",
                        "issuer": "bc1qm4keajcuk5u5qdvpx5kaglghahxp8v4q96mdmc",
                        "transfer": False,
                        "callable": False,
                        "call_date": 0,
                        "call_price": 0.0,
                        "description": "STAMP:iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
                        "fee_paid": 0,
                        "locked": True,
                        "reset": False,
                        "status": "valid",
                    },
                    "tx_hash": "a28a6453d4265cd01e2a7b31f8502c1b58e8b3251bc45f4d96f5c4a10de088d8",
                    "block_index": 784320,
                },
                {
                    "event_index": 2304004,
                    "event": "DEBIT",
                    "params": {
                        "address": "bc1qm4keajcuk5u5qdvpx5kaglghahxp8v4q96mdmc",
                        "asset": "XCP",
                        "quantity": 50000000,
                        "action": "issuance fee",
                        "event": "a28a6453d4265cd01e2a7b31f8502c1b58e8b3251bc45f4d96f5c4a10de088d8",
                    },
                    "tx_hash": "a28a6453d4265cd01e2a7b31f8502c1b58e8b3251bc45f4d96f5c4a10de088d8",
                    "block_index": 784320,
                },
            ],
            "next_cursor": None,
            "result_count": 2,
        }

        # Mock verbose=true response (combines transactions with events)
        verbose_response = {
            "result": [
                {
                    **transactions_response["result"][0],
                    "events": [events_response["result"][0], events_response["result"][1]],
                    "unpacked_data": {},
                    "btc_amount_normalized": "0.00000000",
                },
                {
                    **transactions_response["result"][1],
                    "events": [],
                    "unpacked_data": {},
                    "btc_amount_normalized": "0.00000000",
                },
            ],
            "next_cursor": None,
            "result_count": 2,
        }

        return {
            "transactions": transactions_response,
            "events": events_response,
            "verbose": verbose_response,
        }

    @pytest.mark.asyncio
    async def test_workaround_method_structure(self, mock_api_responses):
        """Test that workaround method produces correct data structure."""
        with patch("src.index_core.fetch_utils.fetch_xcp_async") as mock_fetch:
            # Set up mock responses
            async def mock_fetch_impl(endpoint, params=None, timeout=None):
                if "/transactions" in endpoint:
                    return mock_api_responses["transactions"]
                elif "/events" in endpoint:
                    return mock_api_responses["events"]
                return None

            mock_fetch.side_effect = mock_fetch_impl

            # Test workaround method
            result = await _fetch_block_transactions_workaround(784320)

            assert result is not None
            assert result["block_index"] == 784320
            assert len(result["transactions"]) == 2
            assert len(result["issuances"]) == 1

            # Verify transaction has events
            tx_with_events = result["transactions"][0]
            assert "events" in tx_with_events
            assert len(tx_with_events["events"]) == 2

            # Verify issuance parsing
            issuance = result["issuances"][0]
            assert issuance["cpid"] == "A1937300887712877300"
            assert "STAMP:" in issuance["description"]

    @pytest.mark.asyncio
    async def test_original_method_structure(self, mock_api_responses):
        """Test that original method produces correct data structure."""
        with patch("src.index_core.fetch_utils.fetch_xcp_async") as mock_fetch:
            mock_fetch.return_value = mock_api_responses["verbose"]

            # Test original method
            result = await _fetch_block_transactions_original(784320)

            assert result is not None
            assert result["block_index"] == 784320
            assert len(result["transactions"]) == 2
            assert len(result["issuances"]) == 1

            # Verify transaction has events
            tx_with_events = result["transactions"][0]
            assert "events" in tx_with_events
            assert len(tx_with_events["events"]) == 2

    @pytest.mark.asyncio
    async def test_methods_produce_identical_results(self, mock_api_responses):
        """Test that both methods produce identical results."""
        # Mock for workaround method
        with patch("src.index_core.fetch_utils.fetch_xcp_async") as mock_fetch:
            async def mock_fetch_impl(endpoint, params=None, timeout=None):
                if "/transactions" in endpoint and params.get("verbose") == "false":
                    return mock_api_responses["transactions"]
                elif "/events" in endpoint:
                    return mock_api_responses["events"]
                elif "/transactions" in endpoint and params.get("verbose") == "true":
                    return mock_api_responses["verbose"]
                return None

            mock_fetch.side_effect = mock_fetch_impl

            # Get results from both methods
            workaround_result = await _fetch_block_transactions_workaround(784320)
            original_result = await _fetch_block_transactions_original(784320)

            # Both should succeed
            assert workaround_result is not None
            assert original_result is not None

            # Compare basic structure
            assert workaround_result["block_index"] == original_result["block_index"]
            assert workaround_result["xcp_block_hash"] == original_result["xcp_block_hash"]
            assert len(workaround_result["transactions"]) == len(original_result["transactions"])
            assert len(workaround_result["issuances"]) == len(original_result["issuances"])

            # Compare transactions
            for i, (tx1, tx2) in enumerate(
                zip(workaround_result["transactions"], original_result["transactions"])
            ):
                assert tx1["tx_hash"] == tx2["tx_hash"], f"Transaction {i} hash mismatch"
                assert tx1["transaction_type"] == tx2["transaction_type"], f"Transaction {i} type mismatch"
                assert len(tx1.get("events", [])) == len(tx2.get("events", [])), f"Transaction {i} events count mismatch"

    @pytest.mark.asyncio
    async def test_configuration_flag_switching(self, mock_api_responses):
        """Test that configuration flag correctly switches between methods."""
        with patch("src.index_core.fetch_utils.fetch_xcp_async") as mock_fetch:
            async def mock_fetch_impl(endpoint, params=None, timeout=None):
                if "/transactions" in endpoint and params.get("verbose") == "false":
                    return mock_api_responses["transactions"]
                elif "/events" in endpoint:
                    return mock_api_responses["events"]
                elif "/transactions" in endpoint and params.get("verbose") == "true":
                    return mock_api_responses["verbose"]
                return None

            mock_fetch.side_effect = mock_fetch_impl

            # Test with workaround enabled
            with patch("src.config.CP_API_USE_VERBOSE_WORKAROUND", True):
                result = await fetch_block_transactions_with_pagination(784320)
                assert result is not None
                # Should have called transactions endpoint with verbose=false
                calls = [call for call in mock_fetch.call_args_list if "/transactions" in call[0][0]]
                assert any(call[0][1].get("verbose") == "false" for call in calls)

            mock_fetch.reset_mock()

            # Test with workaround disabled
            with patch("src.config.CP_API_USE_VERBOSE_WORKAROUND", False):
                result = await fetch_block_transactions_with_pagination(784320)
                assert result is not None
                # Should have called transactions endpoint with verbose=true
                calls = [call for call in mock_fetch.call_args_list if "/transactions" in call[0][0]]
                assert any(call[0][1].get("verbose") == "true" for call in calls)

    @pytest.mark.asyncio
    async def test_workaround_handles_missing_events(self):
        """Test that workaround method handles transactions without events."""
        with patch("src.index_core.fetch_utils.fetch_xcp_async") as mock_fetch:
            # Mock responses with no events
            async def mock_fetch_impl(endpoint, params=None, timeout=None):
                if "/transactions" in endpoint:
                    return {
                        "result": [
                            {
                                "tx_hash": "test123",
                                "block_index": 784320,
                                "transaction_type": "send",
                            }
                        ],
                        "next_cursor": None,
                    }
                elif "/events" in endpoint:
                    return {"result": [], "next_cursor": None}
                return None

            mock_fetch.side_effect = mock_fetch_impl

            result = await _fetch_block_transactions_workaround(784320)

            assert result is not None
            assert len(result["transactions"]) == 1
            assert result["transactions"][0]["events"] == []  # Should have empty events array

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_real_api_comparison(self):
        """
        Integration test comparing real API responses.
        
        This test is marked as integration and will only run with --integration flag.
        It tests against the real Counterparty API to ensure both methods work correctly.
        """
        # Test with a small block that should work with both methods
        test_block = 784325  # Known to have only 14 transactions

        workaround_result = await _fetch_block_transactions_workaround(test_block)
        
        # Only test original method if it's expected to work (small block)
        original_result = None
        try:
            original_result = await _fetch_block_transactions_original(test_block)
        except Exception as e:
            pytest.skip(f"Original method failed (expected with current API bug): {e}")

        if workaround_result and original_result:
            # Compare results
            assert workaround_result["block_index"] == original_result["block_index"]
            assert len(workaround_result["transactions"]) == len(original_result["transactions"])
            
            # Check that all transactions have the same tx_hash
            workaround_hashes = {tx["tx_hash"] for tx in workaround_result["transactions"]}
            original_hashes = {tx["tx_hash"] for tx in original_result["transactions"]}
            assert workaround_hashes == original_hashes, "Transaction hashes don't match between methods"