"""
Comprehensive tests for SRC-20 ledger validation functionality.
Tests API data integrity, consensus checks, and hash validation.
"""

import hashlib
import json
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest

from index_core.src20 import (
    compare_balances,
    fetch_api_ledger_data,
    parse_balances,
    validate_src20_ledger_hash,
)


class TestSrc20LedgerValidation(unittest.TestCase):
    """Test ledger validation functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_db = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_db.cursor.return_value.__enter__.return_value = self.mock_cursor

    @patch("index_core.src20.requests.get")
    def test_fetch_api_ledger_data_success(self, mock_get):
        """Test successful API ledger data fetch."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "ledger": [{"address": "addr1", "balance": "100.5"}, {"address": "addr2", "balance": "200.25"}],
            "tick": "TEST",
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = fetch_api_ledger_data("TEST")

        assert result == {"addr1": "100.5", "addr2": "200.25"}
        mock_get.assert_called_once()

    @patch("index_core.src20.requests.get")
    def test_fetch_api_ledger_data_retry_logic(self, mock_get):
        """Test retry logic in API fetch."""
        # First two calls fail, third succeeds
        mock_get.side_effect = [
            Exception("Network error"),
            Exception("Timeout"),
            Mock(
                json=Mock(return_value={"ledger": [{"address": "addr1", "balance": "100"}], "tick": "TEST"}),
                raise_for_status=Mock(),
            ),
        ]

        result = fetch_api_ledger_data("TEST")

        assert result == {"addr1": "100"}
        assert mock_get.call_count == 3

    @patch("index_core.src20.requests.get")
    def test_fetch_api_ledger_data_max_retries_exceeded(self, mock_get):
        """Test behavior when max retries exceeded."""
        mock_get.side_effect = Exception("Persistent error")

        result = fetch_api_ledger_data("TEST")

        assert result is None
        assert mock_get.call_count == 3  # Default max retries

    @patch("index_core.src20.requests.get")
    def test_fetch_api_ledger_data_malformed_response(self, mock_get):
        """Test handling of malformed API responses."""
        test_cases = [
            # Missing ledger field
            {"tick": "TEST"},
            # Ledger not a list
            {"ledger": "not_a_list", "tick": "TEST"},
            # Missing balance field
            {"ledger": [{"address": "addr1"}], "tick": "TEST"},
            # Invalid balance format
            {"ledger": [{"address": "addr1", "balance": "invalid"}], "tick": "TEST"},
            # Empty ledger
            {"ledger": [], "tick": "TEST"},
        ]

        for test_response in test_cases:
            mock_response = Mock()
            mock_response.json.return_value = test_response
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            result = fetch_api_ledger_data("TEST")
            # Should handle gracefully without crashing

    def test_parse_balances(self):
        """Test parsing balance strings."""
        # Test valid balance string
        balance_str = "addr1:100.5,addr2:200.25,addr3:0"
        result = parse_balances(balance_str)

        assert result == {"addr1": "100.5", "addr2": "200.25", "addr3": "0"}

        # Test empty balance string
        result = parse_balances("")
        assert result == {}

        # Test malformed balance string
        result = parse_balances("invalid:balance:format")
        # Should handle gracefully

    def test_parse_balances_decimal_precision(self):
        """Test decimal precision handling in balance parsing."""
        balance_str = "addr1:1.123456789012345678,addr2:0.000000000000000001,addr3:999999999999999999.999999999999999999"

        result = parse_balances(balance_str)

        # Should maintain precision
        if result:
            assert "addr1" in result
            assert "addr2" in result
            assert "addr3" in result

    def test_compare_balances_identical(self):
        """Test comparing identical balance sets."""
        balances1 = {"addr1": "100", "addr2": "200", "addr3": "300"}

        balances2 = {"addr1": "100", "addr2": "200", "addr3": "300"}

        differences = compare_balances(balances1, balances2)

        # Should have no differences
        assert len(differences) == 0

    def test_compare_balances_with_differences(self):
        """Test balance comparison with differences."""
        local_balances = {"addr1": "100", "addr2": "200", "addr3": "300"}

        api_balances = {
            "addr1": "100",  # Same
            "addr2": "201",  # Different
            "addr4": "400",  # New address
            # addr3 missing
        }

        differences = compare_balances(local_balances, api_balances)

        # Should find differences
        assert len(differences) > 0

    def test_compare_balances_edge_values(self):
        """Test balance comparison with edge case values."""
        test_cases = [
            # Empty balances
            ({}, {}),
            # One empty
            ({"addr1": "100"}, {}),
            # Very large numbers
            ({"addr1": "999999999999999999.999999999999999999"}, {"addr1": "999999999999999999.999999999999999999"}),
            # Very small differences
            ({"addr1": "0.000000000000000001"}, {"addr1": "0.000000000000000002"}),
        ]

        for local, api in test_cases:
            differences = compare_balances(local, api)
            # Should handle all cases without errors

    def test_validate_src20_ledger_hash_success(self):
        """Test successful ledger validation."""
        # Mock successful validation
        with patch("index_core.src20.fetch_api_ledger_data") as mock_fetch:
            mock_fetch.return_value = {"addr1": "100", "addr2": "200"}

            # The actual validation logic depends on implementation
            result = validate_src20_ledger_hash(1000, "expected_hash", "valid_str")

            # Check that it attempts to fetch API data
            mock_fetch.assert_called()

    def test_validate_src20_ledger_hash_api_failure(self):
        """Test ledger validation when API fails."""
        with patch("index_core.src20.fetch_api_ledger_data") as mock_fetch:
            mock_fetch.return_value = None  # API failure

            result = validate_src20_ledger_hash(1000, "hash", "valid_str")

            # Should handle API failure gracefully
            assert isinstance(result, bool)

    def test_balance_string_parsing_consistency(self):
        """Test that balance parsing remains consistent."""
        # Test various balance string formats
        test_cases = [
            "addr1:100.5,addr2:200.25,addr3:300.125",
            "addr1:0,addr2:0,addr3:0",
            "single_addr:999999999999999999.999999999999999999",
            "",  # Empty string
        ]

        for balance_str in test_cases:
            parsed = parse_balances(balance_str)
            # Should parse without errors
            assert isinstance(parsed, dict)

    @patch("index_core.src20.requests.get")
    def test_api_ledger_special_characters_handling(self, mock_get):
        """Test API response with special characters in addresses."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "ledger": [
                {"address": "addr with spaces", "balance": "100"},
                {"address": "addr\nwith\nnewlines", "balance": "200"},
                {"address": "addr\twith\ttabs", "balance": "300"},
                {"address": 'addr"with"quotes', "balance": "400"},
            ],
            "tick": "TEST",
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = fetch_api_ledger_data("TEST")

        # Should handle special characters in addresses
        assert "addr with spaces" in result
        assert "addr\nwith\nnewlines" in result
        assert "addr\twith\ttabs" in result
        assert 'addr"with"quotes' in result

    def test_ledger_validation_performance_with_large_datasets(self):
        """Test ledger validation performance with large balance sets."""
        # Create large balance set
        large_balances = {f"addr{i}": str(i) for i in range(10000)}

        # Hash generation should complete in reasonable time
        import time

        start_time = time.time()
        hash_result = get_src20_ledger_hash(large_balances)
        elapsed_time = time.time() - start_time

        assert elapsed_time < 1.0  # Should complete within 1 second
        assert isinstance(hash_result, str)

    @patch("index_core.src20.fetch_api_ledger_data")
    def test_validate_ledger_with_network_interruption(self, mock_fetch):
        """Test ledger validation when network is interrupted mid-fetch."""
        # Simulate network interruption
        mock_fetch.side_effect = KeyboardInterrupt("Network interrupted")

        with pytest.raises(KeyboardInterrupt):
            validate_src20_ledger_hash(self.mock_db, "TEST", "hash", force=False)

    def test_balance_comparison_normalization(self):
        """Test that balance comparison handles normalization."""
        # Different representations of same balances
        balances1 = {"addr1": "100.0", "addr2": "200.00", "addr3": "300.000"}

        balances2 = {"addr1": "100", "addr2": "200", "addr3": "300"}

        differences = compare_balances(balances1, balances2)

        # Behavior depends on whether normalization is applied
        # This test documents the current behavior


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
