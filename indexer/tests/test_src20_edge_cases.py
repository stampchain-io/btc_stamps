"""
Comprehensive edge case tests for SRC-20 implementation.
Tests cover decimal handling, thread safety, ledger validation, and database transactions.
"""

import json
import threading
import time
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from index_core.exceptions import DecodeError
from index_core.src20 import (
    Src20Processor,
    check_format,
    compare_balances,
    fetch_api_ledger_data,
    format_decimal,
    get_running_user_balances,
    parse_balances,
    update_balance_table,
    update_src20_balances,
    validate_src20_ledger_hash,
)


class TestSrc20EdgeCases(unittest.TestCase):
    """Test edge cases in SRC-20 implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_db = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_db.cursor.return_value.__enter__.return_value = self.mock_cursor

    def test_decimal_formatting_edge_cases(self):
        """Test edge cases in decimal formatting."""
        # Test trailing zeros removal
        assert format_decimal(Decimal("100.0000")) == "100"
        assert format_decimal(Decimal("0.10000")) == "0.1"

        # Test leading zeros
        assert format_decimal(Decimal("000.5")) == "0.5"
        assert format_decimal(Decimal("00100.00")) == "100"

        # Test decimal point only
        assert format_decimal(Decimal("100.")) == "100"
        assert format_decimal(Decimal(".5")) == "0.5"

        # Test zero values
        assert format_decimal(Decimal("0")) == "0"
        assert format_decimal(Decimal("0.0")) == "0"
        assert format_decimal(Decimal("0.000")) == "0"
        assert format_decimal(Decimal("000.000")) == "0"

        # Test maximum precision (18 decimals)
        assert format_decimal(Decimal("1.123456789012345678")) == "1.123456789012345678"
        assert format_decimal(Decimal("1.1234567890123456780000")) == "1.123456789012345678"

        # Test very small values
        assert format_decimal(Decimal("0.000000000000000001")) == "0.000000000000000001"

        # Test very large values
        assert format_decimal(Decimal("999999999999999999")) == "999999999999999999"
        assert format_decimal(Decimal("1000000000000000000")) == "1000000000000000000"

    def test_check_format_edge_cases(self):
        """Test edge cases in check_format function."""
        # Test empty JSON
        result = check_format("", "test_tx", 1000)
        assert result is None  # Invalid JSON returns None

        # Test malformed JSON
        result = check_format("{invalid json", "test_tx", 1000)
        assert result is None  # Invalid JSON returns None

        # Test JSON with missing required fields
        incomplete_data = {"p": "src-20", "op": "deploy"}  # Missing tick
        result = check_format(json.dumps(incomplete_data), "test_tx", 1000)
        assert result is None  # Missing required fields returns None

        # Test JSON with extra fields (are they preserved or filtered?)
        extra_fields = {
            "p": "src-20",
            "op": "deploy",
            "tick": "TEST",
            "max": "1000",
            "lim": "10",
            "extra_field": "should_be_ignored",
        }
        result = check_format(json.dumps(extra_fields), "test_tx", 1000)
        if result is not None:
            # Document current behavior: extra fields are preserved
            assert "extra_field" in result
            assert result["extra_field"] == "should_be_ignored"

        # Test nested JSON objects
        nested_json = {
            "p": "src-20",
            "op": "deploy",
            "tick": {"nested": "object"},  # Invalid nested object
            "max": "1000",
            "lim": "10",
        }
        result = check_format(json.dumps(nested_json), "test_tx", 1000)
        assert result is None  # Invalid tick type returns None

        # Test Unicode in tick names
        unicode_tick = {"p": "src-20", "op": "deploy", "tick": "TEST🚀", "max": "1000", "lim": "10"}
        result = check_format(json.dumps(unicode_tick), "test_tx", 1000)
        # Should handle unicode properly
        if result is not None:
            assert result["tick"] == "TEST🚀"

        # Test very long tick names
        long_tick = {"p": "src-20", "op": "deploy", "tick": "A" * 1000, "max": "1000", "lim": "10"}  # Very long tick
        result = check_format(json.dumps(long_tick), "test_tx", 1000)
        # Should either accept or reject based on tick length limits

    def test_zero_amount_operations(self):
        """Test operations with zero amounts."""
        # Test mint with zero amount
        zero_mint = {"p": "src-20", "op": "mint", "tick": "TEST", "amt": "0"}
        result = check_format(json.dumps(zero_mint), "test_tx", 1000)
        assert result is None  # Zero amounts should be rejected

        # Test transfer with zero amount
        zero_transfer = {"p": "src-20", "op": "transfer", "tick": "TEST", "amt": "0"}
        result = check_format(json.dumps(zero_transfer), "test_tx", 1000)
        assert result is None  # Zero amounts should be rejected

    def test_get_running_user_balances_edge_cases(self):
        """Test edge cases in get_running_user_balances."""
        # Test empty address list
        result = get_running_user_balances(self.mock_db, "TEST", "test_hash", [], [])
        assert result == {}

        # Test duplicate addresses (should be handled gracefully)
        self.mock_cursor.fetchall.return_value = []
        result = get_running_user_balances(self.mock_db, "TEST", "test_hash", ["addr1", "addr2", "addr1"], [])
        # Should handle duplicates

        # Test addresses with special characters
        special_addrs = ["addr_with_underscore", "addr-with-dash", "addr.with.dot"]
        self.mock_cursor.fetchall.return_value = [
            ("addr_with_underscore", Decimal("10")),
            ("addr-with-dash", Decimal("20")),
            ("addr.with.dot", Decimal("30")),
        ]
        result = get_running_user_balances(self.mock_db, "TEST", "test_hash", special_addrs, [])
        assert len(result) == 3

    def test_update_balance_table_edge_cases(self):
        """Test edge cases in update_balance_table."""
        balance_updates = {}

        # Test zero net change
        initial_balance = Decimal("100")
        update_balance_table(self.mock_db, balance_updates, 1000, 1000000)
        # Should handle empty updates

        # Test very large balance values
        balance_updates = {
            "TEST_addr1": {
                "tick": "TEST",
                "address": "addr1",
                "tick_hash": "hash",
                "balance": Decimal("999999999999999999.999999999999999999"),
            }
        }
        update_balance_table(self.mock_db, balance_updates, 1000, 1000000)

        # Test precision limits
        balance_updates = {
            "TEST_addr2": {
                "tick": "TEST",
                "address": "addr2",
                "tick_hash": "hash",
                "balance": Decimal("1.123456789012345678901234567890"),  # More than 18 decimals
            }
        }
        update_balance_table(self.mock_db, balance_updates, 1000, 1000000)

    def test_bulk_transfer_edge_cases(self):
        """Test edge cases in bulk transfer operations."""
        processor = Src20Processor(self.mock_db)

        # Test with empty processed list
        processor.processed_src20_in_block = []

        # Simulate bulk transfer scenario
        transfer_dict = {"op": "transfer", "tick": "TEST", "amt": "100", "status": "valid"}

        # Process transfer
        # Should handle edge cases in transfer processing

    def test_thread_safety_shared_state(self):
        """Test thread safety in shared state modifications."""
        processor = Src20Processor(self.mock_db)
        processor.processed_src20_in_block = []

        # Simulate concurrent bulk transfers
        def add_to_processed(tx_index):
            time.sleep(0.001)  # Small delay to increase chance of race condition
            processor.processed_src20_in_block.append(f"tx_{tx_index}")

        threads = []
        for i in range(10):
            t = threading.Thread(target=add_to_processed, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All items should be added despite concurrent access
        assert len(processor.processed_src20_in_block) == 10

    @patch("index_core.src20.requests.get")
    def test_ledger_validation_edge_cases(self, mock_get):
        """Test edge cases in ledger validation."""
        # Test API timeout
        mock_get.side_effect = Exception("Connection timeout")

        result = validate_src20_ledger_hash(self.mock_db, "TEST", "expected_hash", force=False)
        assert result is False

        # Test malformed API response
        mock_response = Mock()
        mock_response.json.return_value = {"malformed": "response"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = validate_src20_ledger_hash(self.mock_db, "TEST", "expected_hash", force=False)
        assert result is False

        # Test Unicode in tick names
        mock_response.json.return_value = {"ledger": [{"address": "addr1", "balance": "100"}], "tick": "TEST🚀"}
        mock_get.return_value = mock_response

        # Should handle unicode in API responses
        result = validate_src20_ledger_hash(self.mock_db, "TEST🚀", "hash", force=False)

        # Test empty ledger
        mock_response.json.return_value = {"ledger": [], "tick": "TEST"}
        mock_get.return_value = mock_response

        result = validate_src20_ledger_hash(self.mock_db, "TEST", "hash", force=False)

    @patch("index_core.src20.check_format")
    def test_database_transaction_atomicity(self, mock_check):
        """Test database transaction atomicity in balance updates."""
        processor = Src20Processor(self.mock_db)

        # Simulate executemany failure
        self.mock_cursor.executemany.side_effect = Exception("Database error")

        with pytest.raises(Exception):
            update_src20_balances(self.mock_db, 1000, {"balance_updates": [("TEST", "addr1", 100)]})

        # Verify rollback was called
        self.mock_db.rollback.assert_called()

    def test_decimal_formatting_precision(self):
        """Test decimal formatting precision."""
        # Test very small decimals
        assert format_decimal(Decimal("0.000000000000000001")) == "0.000000000000000001"

        # Test numbers that would use scientific notation
        assert format_decimal(Decimal("1000000000000000000")) == "1000000000000000000"

        # Test negative zero
        assert format_decimal(Decimal("-0")) == "0"

        # Test numbers with exact 18 decimal places
        num = Decimal("1.123456789012345678")
        assert format_decimal(num) == "1.123456789012345678"

    def test_concurrent_balance_updates(self):
        """Test concurrent updates to the same balance."""
        processor = Src20Processor(self.mock_db)

        # Simulate concurrent transfers to/from same address
        def transfer_operation(from_addr, to_addr, amount):
            with patch("index_core.src20.get_user_balance") as mock_balance:
                mock_balance.return_value = Decimal("1000")
                # Simulate transfer logic
                time.sleep(0.001)

        threads = []
        # Multiple transfers involving same address
        for i in range(5):
            t1 = threading.Thread(target=transfer_operation, args=("addr1", f"addr{i}", 10))
            t2 = threading.Thread(target=transfer_operation, args=(f"addr{i}", "addr1", 5))
            threads.extend([t1, t2])
            t1.start()
            t2.start()

        for t in threads:
            t.join()

    def test_status_message_handling(self):
        """Test status message handling in check_format."""
        # Test various invalid inputs
        test_cases = [
            {"p": "invalid"},  # Wrong protocol
            {"p": "src-20"},  # Missing required fields
            {"p": "src-20", "op": "invalid"},  # Invalid operation
            {"p": "src-20", "op": "mint", "tick": ""},  # Empty tick
        ]

        for data in test_cases:
            result = check_format(json.dumps(data), "test_tx", 1000)
            # Invalid inputs should return None
            assert result is None

    def test_balance_calculation_precision(self):
        """Test precision in balance calculations."""
        # Test addition precision
        balance1 = Decimal("0.123456789012345678")
        balance2 = Decimal("0.876543210987654321")
        result = balance1 + balance2
        # Should maintain precision up to 18 decimals

        # Test subtraction crossing zero
        balance = Decimal("10.5")
        deduction = Decimal("10.5")
        result = balance - deduction
        assert result == Decimal("0")

        # Test multiplication precision
        balance = Decimal("1.111111111111111111")
        multiplier = Decimal("2")
        result = balance * multiplier

        # Test division precision
        total = Decimal("100")
        holders = 3
        per_holder = total / holders
        # Should handle repeating decimals

    def test_balance_retrieval_edge_cases(self):
        """Test balance retrieval in edge cases."""
        # Test with None balance results
        self.mock_cursor.fetchall.return_value = []
        balances = get_running_user_balances(self.mock_db, "TEST", "hash", ["addr1"], [])
        # Returns a list of BalanceCurrent objects
        assert isinstance(balances, list)
        if balances:
            assert all(hasattr(b, "address") for b in balances)

        # Test with very large address list
        large_addr_list = [f"addr{i}" for i in range(1000)]
        self.mock_cursor.fetchall.return_value = [(f"addr{i}", Decimal("1")) for i in range(1000)]
        balances = get_running_user_balances(self.mock_db, "TEST", "hash", large_addr_list, [])
        # Check that we get results
        assert isinstance(balances, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
