"""
Test cases for block validation functions that will be extracted from blocks.py

These tests ensure block validation functions work correctly before and after
refactoring to block_validation.py module.
"""

import os
import sys
import unittest.mock as mock
from collections import namedtuple
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config

# Mock ValidStamp namedtuple for testing
ValidStamp = namedtuple("ValidStamp", ["stamp_number", "cpid", "tx_hash", "asset_name", "keyburn", "stamp_base64"])


class TestBlockValidation:
    """Test cases for block validation functions from blocks.py"""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup method run before each test."""
        # Store original config values
        self.original_debug_validation = getattr(config, "DEBUG_VALIDATION", False)
        self.original_src20_genesis = getattr(config, "BTC_SRC20_GENESIS_BLOCK", 900000)

        # Set test config values
        config.DEBUG_VALIDATION = False
        config.BTC_SRC20_GENESIS_BLOCK = 900000

    def teardown_method(self):
        """Cleanup method run after each test."""
        # Restore original config values
        config.DEBUG_VALIDATION = self.original_debug_validation
        config.BTC_SRC20_GENESIS_BLOCK = self.original_src20_genesis

    def test_create_check_hashes_function_exists(self):
        """Test that create_check_hashes function exists and is callable"""
        from index_core.block_validation import create_check_hashes

        # Test that the function exists and is callable
        assert callable(create_check_hashes)

        # Test that it has the expected signature (basic test)
        import inspect

        sig = inspect.signature(create_check_hashes)
        param_names = list(sig.parameters.keys())

        # Verify key parameters exist
        assert "db" in param_names
        assert "block_index" in param_names
        assert "valid_stamps_in_block" in param_names

    def test_create_check_hashes_accepts_previous_hashes(self):
        """Test create_check_hashes accepts previous hash parameters"""
        import inspect

        from index_core.block_validation import create_check_hashes

        sig = inspect.signature(create_check_hashes)
        param_names = list(sig.parameters.keys())

        # Verify optional previous hash parameters exist
        assert "previous_ledger_hash" in param_names
        assert "previous_txlist_hash" in param_names
        assert "previous_messages_hash" in param_names

    def test_create_check_hashes_empty_inputs(self):
        """Test create_check_hashes with empty inputs"""
        from index_core.block_validation import create_check_hashes

        mock_db = Mock()

        with patch("index_core.check.consensus_hash") as mock_consensus_hash, patch(
            "index_core.block_validation.update_block_hashes"
        ) as mock_update_hashes:

            mock_consensus_hash.side_effect = [
                ("empty_txlist", "found_txlist"),
                ("empty_ledger", "found_ledger"),
                ("empty_messages", "found_messages"),
            ]

            result = create_check_hashes(mock_db, 900001, [], [], [])

            assert result == ("empty_ledger", "empty_txlist", "empty_messages")
            mock_update_hashes.assert_called_once()

    def test_create_check_hashes_database_error(self):
        """Test create_check_hashes with database update error"""
        from index_core.block_validation import create_check_hashes
        from index_core.exceptions import BlockUpdateError

        mock_db = Mock()

        with patch("index_core.check.consensus_hash") as mock_consensus_hash, patch(
            "index_core.block_validation.update_block_hashes"
        ) as mock_update_hashes:

            mock_consensus_hash.side_effect = [
                ("hash2", "found_txlist"),
                ("hash1", "found_ledger"),
                ("hash3", "found_messages"),
            ]
            mock_update_hashes.side_effect = BlockUpdateError("Database update failed")

            # Should raise SystemExit with string message
            with pytest.raises(SystemExit, match="Exiting due to a critical update error"):
                create_check_hashes(mock_db, 900001, [], [], [])

    def test_create_check_hashes_stamp_sorting(self):
        """Test create_check_hashes properly sorts stamps by stamp_number"""
        from index_core.block_validation import create_check_hashes

        mock_db = Mock()

        # Create stamps in non-sorted order
        valid_stamps = [
            {
                "stamp_number": 3,
                "cpid": "A125",
                "tx_hash": "tx3",
                "asset_name": "STAMP3",
                "keyburn": 546,
                "stamp_base64": "base64data3",
            },
            {
                "stamp_number": 1,
                "cpid": "A123",
                "tx_hash": "tx1",
                "asset_name": "STAMP1",
                "keyburn": 546,
                "stamp_base64": "base64data1",
            },
            {
                "stamp_number": 2,
                "cpid": "A124",
                "tx_hash": "tx2",
                "asset_name": "STAMP2",
                "keyburn": 546,
                "stamp_base64": "base64data2",
            },
        ]

        with patch("index_core.check.consensus_hash") as mock_consensus_hash, patch(
            "index_core.block_validation.update_block_hashes"
        ) as mock_update_hashes:

            mock_consensus_hash.side_effect = [
                ("hash2", "found_txlist"),
                ("hash1", "found_ledger"),
                ("hash3", "found_messages"),
            ]

            create_check_hashes(mock_db, 900001, valid_stamps, [], [])

            # Verify stamps were sorted before hashing
            # The first call is for txlist_hash with sorted stamps
            txlist_call = mock_consensus_hash.call_args_list[0]
            txlist_content = txlist_call[0][4]  # 5th argument is the content

            # The content should contain stamps in sorted order
            assert "'stamp_number': 1" in txlist_content
            assert "'stamp_number': 2" in txlist_content
            assert "'stamp_number': 3" in txlist_content

            # Verify order by checking positions
            pos1 = txlist_content.find("'stamp_number': 1")
            pos2 = txlist_content.find("'stamp_number': 2")
            pos3 = txlist_content.find("'stamp_number': 3")
            assert pos1 < pos2 < pos3

    def test_validate_block_against_production_disabled(self):
        """Test validate_block_against_production with DEBUG_VALIDATION disabled"""
        from index_core.block_validation import validate_block_against_production

        config.DEBUG_VALIDATION = False

        result = validate_block_against_production(900001)

        # Should return True immediately when disabled
        assert result is True

    def test_validate_block_against_production_success(self):
        """Test validate_block_against_production with successful validation"""
        from index_core.block_validation import validate_block_against_production

        config.DEBUG_VALIDATION = True

        # Mock subprocess to simulate successful validation
        mock_process = Mock()
        mock_process.wait.return_value = 0  # Success
        mock_process.poll.return_value = 0

        with patch("subprocess.Popen") as mock_popen, patch("os.path.exists") as mock_exists, patch(
            "index_core.node_health.is_shutdown_requested"
        ) as mock_is_shutdown:

            mock_popen.return_value = mock_process
            mock_exists.return_value = True  # Script exists
            mock_is_shutdown.return_value = False  # Not shutting down

            result = validate_block_against_production(900001)

            assert result is True
            mock_popen.assert_called_once()

    def test_validate_block_against_production_failure(self):
        """Test validate_block_against_production with validation failure"""
        from index_core.block_validation import validate_block_against_production

        config.DEBUG_VALIDATION = True

        # Mock subprocess to simulate validation failure
        mock_process = Mock()
        mock_process.wait.return_value = 1  # Failure
        mock_process.poll.return_value = 1
        mock_process.communicate.return_value = ("", "Validation failed")  # stdout, stderr

        with patch("subprocess.Popen") as mock_popen, patch("os.path.exists") as mock_exists, patch(
            "index_core.node_health.is_shutdown_requested"
        ) as mock_is_shutdown:

            mock_popen.return_value = mock_process
            mock_exists.return_value = True
            mock_is_shutdown.return_value = False

            result = validate_block_against_production(900001)

            assert result is False

    def test_validate_block_against_production_shutdown_during_validation(self):
        """Test validate_block_against_production with shutdown during validation"""
        from index_core.block_validation import validate_block_against_production

        config.DEBUG_VALIDATION = True

        # Mock subprocess that takes time to complete
        mock_process = Mock()
        mock_process.poll.side_effect = [None, None, 0]  # Running, then complete
        mock_process.wait.return_value = 0

        with patch("subprocess.Popen") as mock_popen, patch("os.path.exists") as mock_exists, patch(
            "index_core.node_health.is_shutdown_requested"
        ) as mock_is_shutdown, patch(
            "time.sleep"
        ):  # Mock sleep to speed up test

            mock_popen.return_value = mock_process
            mock_exists.return_value = True
            mock_is_shutdown.side_effect = [False, True]  # Shutdown requested

            result = validate_block_against_production(900001)

            # Should return True on graceful shutdown
            assert result is True

    def test_validate_block_against_production_script_not_found(self):
        """Test validate_block_against_production with missing script"""
        from index_core.block_validation import validate_block_against_production

        config.DEBUG_VALIDATION = True

        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = False  # Script doesn't exist

            result = validate_block_against_production(900001)

            # Should return True if script not found (skip validation)
            assert result is True

    def test_filter_block_transactions_pre_genesis(self):
        """Test filter_block_transactions with pre-genesis block"""
        from index_core.block_validation import filter_block_transactions

        # Mock block data with transactions
        block_data = {
            "tx": [
                {"txid": "tx1", "hex": "hex1"},
                {"txid": "tx2", "hex": "hex2"},
                {"txid": "tx3", "hex": "hex3"},
            ]
        }

        # Mock stamp issuances (should only include these)
        stamp_issuances = [
            {"tx_hash": "tx1", "cpid": "A123"},
            {"tx_hash": "tx3", "cpid": "A125"},
        ]

        with patch("index_core.util.CURRENT_BLOCK_INDEX", 899999):  # Pre-genesis

            tx_hash_list, raw_transactions = filter_block_transactions(block_data, stamp_issuances)

            # Should include all tx hashes
            assert tx_hash_list == ["tx1", "tx2", "tx3"]

            # Should only include issuance transactions in raw_transactions
            assert "tx1" in raw_transactions
            assert "tx3" in raw_transactions
            assert "tx2" not in raw_transactions
            assert raw_transactions["tx1"] == "hex1"
            assert raw_transactions["tx3"] == "hex3"

    def test_filter_block_transactions_post_genesis_with_rust_parser(self):
        """Test filter_block_transactions post-genesis with Rust parser"""
        from index_core.block_validation import filter_block_transactions

        # Mock block data
        block_data = {
            "tx": [
                {"txid": "tx1", "hex": "hex1"},
                {"txid": "tx2", "hex": "hex2"},
                {"txid": "tx3", "hex": "hex3"},
            ]
        }

        with patch("index_core.util.CURRENT_BLOCK_INDEX", 900001), patch(
            "index_core.block_validation.backend_instance"
        ) as mock_backend:

            # Mock Rust parser availability
            mock_parser = Mock()
            mock_backend._parser = mock_parser

            # Mock parsed transactions with txid attributes
            mock_tx1 = Mock()
            mock_tx1.txid = "tx1"
            mock_tx3 = Mock()
            mock_tx3.txid = "tx3"

            mock_parser.batch_parse_transactions.return_value = [mock_tx1, mock_tx3]

            tx_hash_list, raw_transactions = filter_block_transactions(block_data)

            assert tx_hash_list == ["tx1", "tx2", "tx3"]
            assert raw_transactions == {"tx1": "hex1", "tx3": "hex3"}

            # Verify Rust parser was used
            mock_parser.batch_parse_transactions.assert_called_once()

    def test_filter_block_transactions_post_genesis_without_rust_parser(self):
        """Test filter_block_transactions post-genesis without Rust parser (Python fallback)"""
        from index_core.block_validation import filter_block_transactions

        # Mock block data
        block_data = {
            "tx": [
                {"txid": "tx1", "hex": "hex1"},
                {"txid": "tx2", "hex": "hex2"},
                {"txid": "tx3", "hex": "hex3"},
            ]
        }

        with patch("index_core.util.CURRENT_BLOCK_INDEX", 900001), patch(
            "index_core.block_validation.backend_instance"
        ) as mock_backend, patch("index_core.block_validation.quick_filter_src20_transaction") as mock_filter:

            # Mock no Rust parser available
            mock_backend._parser = None

            # Mock deserialization
            mock_backend.deserialize.side_effect = [
                Mock(),  # ctx for tx1
                Mock(),  # ctx for tx2
                Mock(),  # ctx for tx3
            ]

            # Mock filtering results
            mock_filter.side_effect = [True, False, True]  # tx1 and tx3 pass filter

            tx_hash_list, raw_transactions = filter_block_transactions(block_data)

            assert tx_hash_list == ["tx1", "tx2", "tx3"]
            assert raw_transactions == {"tx1": "hex1", "tx3": "hex3"}

            # Verify Python fallback was used
            assert mock_backend.deserialize.call_count == 3
            assert mock_filter.call_count == 3

    def test_filter_block_transactions_empty_block(self):
        """Test filter_block_transactions with empty block"""
        from index_core.block_validation import filter_block_transactions

        block_data = {"tx": []}

        with patch("index_core.util.CURRENT_BLOCK_INDEX", 900001):

            tx_hash_list, raw_transactions = filter_block_transactions(block_data)

            assert tx_hash_list == []
            assert raw_transactions == {}

    def test_filter_block_transactions_with_stamp_issuances_post_genesis(self):
        """Test filter_block_transactions post-genesis with stamp issuances"""
        from index_core.block_validation import filter_block_transactions

        block_data = {
            "tx": [
                {"txid": "tx1", "hex": "hex1"},
                {"txid": "tx2", "hex": "hex2"},
            ]
        }

        stamp_issuances = [
            {"tx_hash": "tx1", "cpid": "A123"},
        ]

        with patch("index_core.util.CURRENT_BLOCK_INDEX", 900001), patch(
            "index_core.block_validation.backend_instance"
        ) as mock_backend:

            # Mock Rust parser returning only tx2
            mock_parser = Mock()
            mock_backend._parser = mock_parser
            mock_tx2 = Mock()
            mock_tx2.txid = "tx2"
            mock_parser.batch_parse_transactions.return_value = [mock_tx2]

            tx_hash_list, raw_transactions = filter_block_transactions(block_data, stamp_issuances)

            # Should include both issuance tx and filtered tx
            assert tx_hash_list == ["tx1", "tx2"]
            assert raw_transactions == {"tx1": "hex1", "tx2": "hex2"}

    def test_filter_block_transactions_malformed_transaction(self):
        """Test filter_block_transactions with malformed transaction data"""
        from index_core.block_validation import filter_block_transactions

        # Mock transaction without required attributes - use a dict without txid
        block_data = {
            "tx": [
                {"txid": "tx1", "hex": "hex1"},
                {"hex": "hex2"},  # Missing txid - should be handled gracefully
                {"txid": "tx3", "hex": "hex3"},
            ]
        }

        with patch("index_core.util.CURRENT_BLOCK_INDEX", 900001), patch(
            "index_core.block_validation.backend_instance"
        ) as mock_backend:

            mock_backend._parser = None
            mock_backend.deserialize.side_effect = [Mock(), Exception("Bad tx"), Mock()]

            with patch("index_core.transaction_utils.quick_filter_src20_transaction") as mock_filter:
                mock_filter.side_effect = [True, True]  # Only called for valid txs

                # Should raise KeyError for missing txid
                with pytest.raises(KeyError):
                    filter_block_transactions(block_data)


class TestBlockValidationEdgeCases:
    """Test edge cases in block validation functions"""

    def test_create_check_hashes_with_none_stamps(self):
        """Test create_check_hashes with None in stamps list"""
        from index_core.block_validation import create_check_hashes

        mock_db = Mock()

        # Include None in the list (should be filtered out)
        valid_stamps = [
            {
                "stamp_number": 1,
                "cpid": "A123",
                "tx_hash": "tx1",
                "asset_name": "STAMP1",
                "keyburn": 546,
                "stamp_base64": "base64data1",
            },
            None,
            {
                "stamp_number": 2,
                "cpid": "A124",
                "tx_hash": "tx2",
                "asset_name": "STAMP2",
                "keyburn": 546,
                "stamp_base64": "base64data2",
            },
        ]

        with patch("index_core.check.consensus_hash") as mock_consensus_hash, patch(
            "index_core.block_validation.update_block_hashes"
        ) as mock_update_hashes:

            mock_consensus_hash.side_effect = [
                ("hash2", "found_txlist"),
                ("hash1", "found_ledger"),
                ("hash3", "found_messages"),
            ]

            result = create_check_hashes(mock_db, 900001, valid_stamps, [], [])

            # Should handle None values gracefully
            assert result == ("hash1", "hash2", "hash3")

    def test_filter_block_transactions_current_block_index_none(self):
        """Test filter_block_transactions when CURRENT_BLOCK_INDEX is None"""
        from index_core.block_validation import filter_block_transactions

        block_data = {"tx": [{"txid": "tx1", "hex": "hex1"}]}

        with patch("index_core.util.CURRENT_BLOCK_INDEX", None):

            tx_hash_list, raw_transactions = filter_block_transactions(block_data)

            # Should handle None current block gracefully
            assert tx_hash_list == ["tx1"]
            # Behavior depends on None comparison, but should not crash

    def test_validate_block_against_production_process_exception(self):
        """Test validate_block_against_production with subprocess exception"""
        from index_core.block_validation import validate_block_against_production

        config.DEBUG_VALIDATION = True

        with patch("subprocess.Popen") as mock_popen, patch("os.path.exists") as mock_exists:

            mock_exists.return_value = True
            mock_popen.side_effect = Exception("Process creation failed")

            result = validate_block_against_production(900001)

            # Should return True on exception (fail gracefully)
            assert result is True

    def test_create_check_hashes_missing_stamp_number(self):
        """Test create_check_hashes with stamps missing stamp_number field"""
        from index_core.block_validation import create_check_hashes

        mock_db = Mock()

        # Create stamps with missing stamp_number fields
        valid_stamps = [
            {
                "stamp_number": 2,
                "cpid": "A124",
                "tx_hash": "tx2",
                "asset_name": "STAMP2",
                "keyburn": 546,
                "stamp_base64": "base64data2",
            },
            {
                # Missing stamp_number - should use default 0
                "cpid": "A123",
                "tx_hash": "tx1",
                "asset_name": "STAMP1",
                "keyburn": 546,
                "stamp_base64": "base64data1",
            },
            {
                "stamp_number": 3,
                "cpid": "A125",
                "tx_hash": "tx3",
                "asset_name": "STAMP3",
                "keyburn": 546,
                "stamp_base64": "base64data3",
            },
        ]

        with patch("index_core.check.consensus_hash") as mock_consensus_hash, patch(
            "index_core.block_validation.update_block_hashes"
        ) as mock_update_hashes:

            mock_consensus_hash.side_effect = [
                ("hash2", "found_txlist"),
                ("hash1", "found_ledger"),
                ("hash3", "found_messages"),
            ]

            result = create_check_hashes(mock_db, 900001, valid_stamps, [], [])

            # Verify stamps were sorted correctly with missing stamp_number defaulting to 0
            txlist_call = mock_consensus_hash.call_args_list[0]
            txlist_content = txlist_call[0][4]  # 5th argument is the content

            # The stamp without stamp_number should come first (default 0)
            # Then stamp_number: 2, then stamp_number: 3
            pos_missing = txlist_content.find("'tx_hash': 'tx1'")  # The one without stamp_number
            pos2 = txlist_content.find("'stamp_number': 2")
            pos3 = txlist_content.find("'stamp_number': 3")

            # Verify ordering: missing (0) < 2 < 3
            assert pos_missing < pos2 < pos3
            assert result == ("hash1", "hash2", "hash3")


if __name__ == "__main__":
    pytest.main([__file__])
