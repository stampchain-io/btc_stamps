"""
Test cases for transaction processing functions that will be extracted from blocks.py

These tests ensure transaction processing functions work correctly before and after
refactoring to transaction_utils.py module.
"""

import os
import sys
import unittest.mock as mock
from collections import namedtuple
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config


class TestTransactionProcessing:
    """Test cases for transaction processing functions from blocks.py"""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup method run before each test."""
        # Store original config values
        self.original_prefix = getattr(config, "PREFIX", b"\x45\x4e\x44\x00")
        self.original_olga_block = getattr(config, "BTC_SRC20_OLGA_BLOCK", 900000)

        # Set test config values
        config.PREFIX = b"\x45\x4e\x44\x00"
        config.BTC_SRC20_OLGA_BLOCK = 900002  # Set higher than test block to ensure is_olga is False
        config.BTC_SRC101_OLGA_BLOCK = 900002

    def teardown_method(self):
        """Cleanup method run after each test."""
        # Restore original config values
        config.PREFIX = self.original_prefix
        config.BTC_SRC20_OLGA_BLOCK = self.original_olga_block

    def test_process_vout_with_multisig_output(self):
        """Test process_vout with multisig output containing stamp data"""
        # Import the function we're testing
        from index_core.transaction_utils import process_vout

        # Create mock transaction context
        mock_vout = Mock()
        mock_vout.scriptPubKey = b"\x51\x41\x04..."  # Mock script
        mock_vout.nValue = 1000

        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout]

        # Mock script analysis functions
        with patch("index_core.script.get_asm") as mock_get_asm, patch(
            "index_core.script.get_checkmultisig"
        ) as mock_get_multisig, patch("index_core.script.get_p2wsh") as mock_get_p2wsh:

            # Setup mocks
            mock_get_asm.return_value = ["OP_1", "pubkey1", "pubkey2", "OP_2", "OP_CHECKMULTISIG"]
            mock_get_multisig.return_value = (["pubkey1", "pubkey2"], 1, 546)
            mock_get_p2wsh.return_value = []

            # Test the function
            result = process_vout(mock_ctx, 900001)

            # Verify results
            assert result.pubkeys_compiled == ["pubkey1", "pubkey2"]
            assert result.keyburn == 546
            assert result.is_op_return is None  # OP_RETURN detection may return None for non-OP_RETURN
            assert result.fee == 1000
            assert result.is_olga is False  # Pre-OLGA block behavior
            assert result.p2wsh_data_chunks == []

    def test_process_vout_with_op_return(self):
        """Test process_vout with OP_RETURN output"""
        from index_core.transaction_utils import process_vout

        # Create mock OP_RETURN output
        mock_vout = Mock()
        mock_vout.scriptPubKey = b"\x6a\x20..."  # OP_RETURN script
        mock_vout.nValue = 0

        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout]

        with patch("index_core.script.get_asm") as mock_get_asm:
            # Setup for OP_RETURN detection - original logic checks asm[0] == "OP_RETURN"
            mock_get_asm.return_value = ["OP_RETURN", "data"]

            result = process_vout(mock_ctx, 900001)

            assert result.is_op_return is True
            assert result.keyburn is None  # Original behavior: None, not 0
            assert result.fee == 0

    def test_process_vout_with_p2wsh_data_chunks(self):
        """Test process_vout collecting P2WSH data chunks for SRC-20 transactions"""
        from index_core.transaction_utils import process_vout

        # Create mock P2WSH outputs - original logic: asm[0] == 0 and len(asm[1]) == 32
        mock_vout1 = Mock()
        mock_vout1.scriptPubKey = b"\x00\x20..."
        mock_vout1.nValue = 546

        mock_vout2 = Mock()
        mock_vout2.scriptPubKey = b"\x00\x20..."
        mock_vout2.nValue = 546

        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout1, mock_vout2]

        with patch("index_core.script.get_asm") as mock_get_asm:
            # Original logic: asm[0] == 0 and len(asm[1]) == 32
            # Only processes outputs after first one (idx > 0) for OLGA blocks
            mock_get_asm.side_effect = [
                [0, b"\x12\x34" * 16],  # First output - won't be processed (idx == 0)
                [0, b"\x56\x78" * 16],  # Second output - will be processed (idx > 0)
            ]

            # Test with block at OLGA height
            result = process_vout(mock_ctx, config.BTC_SRC20_OLGA_BLOCK + 1)

            # Should only capture data from second output (idx > 0)
            assert len(result.p2wsh_data_chunks) == 1
            assert result.p2wsh_data_chunks[0] == b"\x56\x78" * 16
            assert result.is_olga is True

    def test_decode_checkmultisig_valid_data(self):
        """Test decode_checkmultisig with valid encrypted data"""
        from index_core.transaction_utils import decode_checkmultisig

        # Create mock context with proper structure
        mock_vin = Mock()
        mock_vin.prevout.hash = b"\x12\x34" * 16  # 32 bytes
        mock_vout = Mock()
        mock_vout.scriptPubKey = b"test_script"
        mock_vout.nValue = 12345

        mock_ctx = Mock()
        mock_ctx.vin = [mock_vin]
        mock_ctx.vout = [mock_vout]

        # Create test chunk that will decrypt to valid format matching original logic
        test_data = b"test_stamp_data"
        # Original expects: 2-byte length + PREFIX + data
        chunk_length = (len(config.PREFIX) + len(test_data)).to_bytes(2, "big")
        decrypted_chunk = chunk_length + config.PREFIX + test_data

        with patch("index_core.arc4.init_arc4") as mock_init_arc4, patch(
            "index_core.arc4.arc4_decrypt_chunk"
        ) as mock_decrypt, patch("index_core.util.decode_address") as mock_decode_addr:

            # Setup mocks - arc4 should be called with reversed hash
            mock_init_arc4.return_value = "test_key"
            mock_decrypt.return_value = decrypted_chunk
            mock_decode_addr.return_value = "test_address"

            destination, nvalue, data = decode_checkmultisig(mock_ctx, b"encrypted_chunk")

            # Verify ARC4 called with reversed hash
            mock_init_arc4.assert_called_once_with(mock_vin.prevout.hash[::-1])
            assert destination == "test_address"
            assert nvalue == 12345
            assert data == test_data.rstrip(b"\x00")

    def test_decode_checkmultisig_invalid_prefix(self):
        """Test decode_checkmultisig with invalid prefix returns None"""
        from index_core.transaction_utils import decode_checkmultisig

        # Create mock context with proper structure
        mock_vin = Mock()
        mock_vin.prevout.hash = b"\x12\x34" * 16
        mock_vout = Mock()
        mock_vout.scriptPubKey = b"test_script"
        mock_vout.nValue = 12345

        mock_ctx = Mock()
        mock_ctx.vin = [mock_vin]
        mock_ctx.vout = [mock_vout]

        # Test chunk that decrypts to invalid prefix
        decrypted_chunk = b"\x00\x20" + b"INVALID" + b"test_data"

        with patch("index_core.arc4.init_arc4") as mock_init_arc4, patch("index_core.arc4.arc4_decrypt_chunk") as mock_decrypt:

            mock_init_arc4.return_value = "test_key"
            mock_decrypt.return_value = decrypted_chunk

            # Should return None, None, None for invalid prefix
            destination, nvalue, data = decode_checkmultisig(mock_ctx, b"encrypted_chunk")

            assert destination is None
            assert nvalue is None
            assert data is None

    def test_get_tx_info_with_stamp_issuance(self):
        """Test get_tx_info with stamp issuance"""
        from index_core.transaction_utils import get_tx_info

        # Mock transaction hex
        test_tx_hex = "0100000001..."  # Simplified hex

        with patch("index_core.transaction_utils.backend_instance") as mock_backend, patch(
            "index_core.transaction_utils.process_vout"
        ) as mock_process_vout, patch("index_core.util.CURRENT_BLOCK_INDEX", 900001), patch(
            "index_core.util.ib2h"
        ) as mock_ib2h:

            # Mock backend response
            mock_ctx = Mock()
            mock_vin = Mock()
            mock_vin.prevout.hash = b"\xab\xcd" * 16
            mock_vin.prevout.n = 0
            mock_ctx.vin = [mock_vin]
            mock_ctx.vout = [Mock()]
            mock_ctx.hash = b"\x12\x34" * 16
            mock_backend.deserialize.return_value = mock_ctx

            # Mock getrawtransaction for source extraction
            mock_backend.getrawtransaction.return_value = "source_tx_hex"

            # Mock process_vout result - pubkeys should be bytes
            mock_vout_info = Mock()
            mock_vout_info.pubkeys_compiled = [b"pubkey1"]
            mock_vout_info.keyburn = 546
            mock_vout_info.is_op_return = False
            mock_vout_info.fee = 1000
            mock_vout_info.p2wsh_data_chunks = []
            mock_process_vout.return_value = mock_vout_info

            mock_ib2h.return_value = "txhash"

            result = get_tx_info(test_tx_hex, block_index=900001, stamp_issuance=True)

            # Verify TransactionInfo structure matches original
            assert hasattr(result, "source")
            assert hasattr(result, "destinations")  # Original field name
            assert hasattr(result, "btc_amount")
            assert hasattr(result, "fee")
            assert hasattr(result, "data")
            assert result.keyburn == 546

            # For stamp issuance, deserialize is called once (early return in original logic)
            assert mock_backend.deserialize.call_count == 1
            mock_backend.deserialize.assert_called_once_with(test_tx_hex)

    def test_list_tx_valid_transaction(self):
        """Test list_tx with valid transaction"""
        from index_core.transaction_utils import list_tx

        mock_db = Mock()
        test_tx_hash = "test_hash"
        test_tx_hex = "0100000001abcd1234" * 20  # Valid hex

        with patch("index_core.transaction_utils.backend_instance") as mock_backend, patch(
            "index_core.transaction_utils.process_vout"
        ) as mock_process_vout, patch("index_core.util.CURRENT_BLOCK_INDEX", 900001), patch(
            "index_core.util.decode_address"
        ) as mock_decode_address, patch(
            "index_core.util.ib2h"
        ) as mock_ib2h:

            # Mock transaction context
            mock_ctx = Mock()
            mock_vin = Mock()
            mock_vin.prevout.hash = b"prev_hash"
            mock_vin.prevout.n = 0
            mock_ctx.vin = [mock_vin]
            mock_ctx.vout = [Mock()]

            # Mock backend deserialize
            mock_backend.deserialize.return_value = mock_ctx
            mock_backend.getrawtransaction.return_value = "source_tx_hex"

            # Mock ib2h for prev_tx_hash - should convert bytes to hex string
            mock_ib2h.return_value = "prev_tx_hash"

            # Mock decode_address
            mock_decode_address.return_value = "source_address"

            # Mock process_vout result - pubkeys should be bytes
            mock_vout_info = Mock()
            mock_vout_info.pubkeys_compiled = [b"pubkey_data"]
            mock_vout_info.keyburn = 546
            mock_vout_info.is_op_return = False
            mock_vout_info.fee = 1000
            mock_vout_info.p2wsh_data_chunks = []
            mock_process_vout.return_value = mock_vout_info

            # Mock decode_checkmultisig
            with patch("index_core.transaction_utils.decode_checkmultisig") as mock_decode:
                mock_decode.return_value = ("dest_address", 5000, b"test_data")

                result = list_tx(mock_db, 900001, test_tx_hash, test_tx_hex)

                # Verify result tuple structure matches original function return order
                assert len(result) == 11
                assert result[0] == "source_address"  # source
                assert result[1] == b"prev_hash"  # prev_tx_hash (bytes from vin.prevout.hash)
                assert result[2] == "dest_address"  # destination
                assert result[3] == 5000  # destination_nvalue
                assert result[4] == 0  # btc_amount
                assert result[5] == 1000  # fee
                assert result[6] == b"test_data"  # data

    def test_list_tx_no_data_transaction(self):
        """Test list_tx with transaction that has no relevant data"""
        from index_core.transaction_utils import list_tx

        mock_db = Mock()
        test_tx_hash = "test_hash"
        test_tx_hex = "0100000001abcd1234" * 20  # Valid hex

        with patch("index_core.transaction_utils.backend_instance") as mock_backend, patch(
            "index_core.transaction_utils.process_vout"
        ) as mock_process_vout, patch("index_core.util.CURRENT_BLOCK_INDEX", 900001):

            # Mock transaction context with no vin (no source)
            mock_ctx = Mock()
            mock_ctx.vin = []
            mock_ctx.vout = [Mock()]

            # Mock backend deserialize
            mock_backend.deserialize.return_value = mock_ctx

            # Mock process_vout result with no relevant data
            mock_vout_info = Mock()
            mock_vout_info.pubkeys_compiled = []
            mock_vout_info.keyburn = 0
            mock_vout_info.is_op_return = None
            mock_vout_info.fee = 0
            mock_vout_info.p2wsh_data_chunks = []
            mock_process_vout.return_value = mock_vout_info

            result = list_tx(mock_db, 900001, test_tx_hash, test_tx_hex)

            # Should return tuple of None values
            assert isinstance(result, tuple)
            assert len(result) == 11
            assert all(item is None for item in result)

    def test_process_tx_with_matching_issuance(self):
        """Test process_tx with matching stamp issuance"""
        from index_core.transaction_utils import process_tx

        mock_db = Mock()
        test_tx_hash = "test_hash"
        test_block_index = 900001

        # Mock stamp issuance data
        stamp_issuances = [
            {"tx_hash": "other_hash", "cpid": "A1234"},
            {"tx_hash": "test_hash", "cpid": "A5678"},
        ]
        raw_transactions = {test_tx_hash: "0100000001..."}

        with patch("index_core.transaction_utils.list_tx") as mock_list_tx, patch(
            "index_core.fetch_utils.find_issuance_by_tx_hash"
        ) as mock_find_issuance:

            # Mock list_tx result in the original order:
            # source, prev_tx_hash, destination, destination_nvalue, btc_amount, fee, data, decoded_tx, keyburn, is_op_return, p2wsh_data
            mock_list_tx.return_value = ("source", None, "dest", None, 1000, 546, b"data", None, 0, False, None)

            # Mock find_issuance_by_tx_hash
            mock_find_issuance.return_value = {"cpid": "A5678"}

            result = process_tx(mock_db, test_tx_hash, test_block_index, stamp_issuances, raw_transactions)

            # Verify TxResult structure
            assert hasattr(result, "source")
            assert hasattr(result, "destination")
            assert hasattr(result, "btc_amount")
            assert hasattr(result, "fee")
            assert hasattr(result, "data")
            assert result.source == "source"
            assert result.destination == "dest"

    def test_quick_filter_src20_transaction_valid_p2wsh(self):
        """Test quick_filter_src20_transaction with valid P2WSH transaction"""
        from index_core.transaction_utils import quick_filter_src20_transaction

        # Create P2WSH output with correct format
        # P2WSH script: 0x00 0x20 <32-byte-hash>
        # Include the STAMP prefix in the data
        p2wsh_data = config.PREFIX + b"test_src20_data"
        # Pad to 32 bytes
        p2wsh_data_padded = p2wsh_data + b"\x00" * (32 - len(p2wsh_data))

        # Create the scriptPubKey
        mock_vout = Mock()
        mock_vout.scriptPubKey = Mock()
        # P2WSH format: 0x00 0x20 followed by 32 bytes of data
        script_hex = "0020" + p2wsh_data_padded.hex()
        mock_vout.scriptPubKey.hex = Mock(return_value=script_hex)

        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout]
        mock_ctx.GetHash = Mock(return_value=b"test_tx_hash")

        result = quick_filter_src20_transaction(mock_ctx)

        # Should return True because it found P2WSH pattern with STAMP prefix
        assert result is True

    def test_quick_filter_src20_transaction_valid_multisig(self):
        """Test quick_filter_src20_transaction with valid multisig transaction"""
        from index_core.transaction_utils import quick_filter_src20_transaction

        # Create multisig output - ends with 0xAE (OP_CHECKMULTISIG)
        mock_vout = Mock()
        mock_vout.scriptPubKey = Mock()
        # Create a valid multisig script ending with 0xAE
        # Format: OP_1 <pubkey> <pubkey> OP_2 OP_CHECKMULTISIG
        script_hex = "5141044e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d41044d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d4e4d52ae"
        mock_vout.scriptPubKey.hex = Mock(return_value=script_hex)

        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout]
        mock_ctx.GetHash = Mock(return_value=b"test_tx_hash")

        # Add mock vin for ARC4 decryption
        mock_vin = Mock()
        mock_vin.prevout.hash = b"\x12\x34" * 16
        mock_ctx.vin = [mock_vin]

        with patch("index_core.script.get_asm") as mock_get_asm, patch(
            "index_core.script.get_checkmultisig"
        ) as mock_get_multisig, patch("index_core.arc4.init_arc4") as mock_init_arc4, patch(
            "index_core.arc4.arc4_decrypt_chunk"
        ) as mock_decrypt:

            # Setup mocks for valid multisig with keyburn
            mock_get_asm.return_value = ["OP_1", "pubkey1", "pubkey2", "OP_2", "OP_CHECKMULTISIG"]
            mock_get_multisig.return_value = (
                [b"\x41" + b"pubkey1_data" + b"\x41", b"\x41" + b"pubkey2_data" + b"\x41"],
                1,
                1,
            )  # keyburn = 1

            # Mock successful decryption with proper format:
            # 2-byte length + PREFIX + data
            decrypted_data = b"test_data"
            chunk_length = len(config.PREFIX) + len(decrypted_data)
            decrypted_chunk = chunk_length.to_bytes(2, "big") + config.PREFIX + decrypted_data

            mock_init_arc4.return_value = "test_key"
            mock_decrypt.return_value = decrypted_chunk

            result = quick_filter_src20_transaction(mock_ctx)

            # Should return True because it found valid multisig with keyburn and valid data
            assert result is True

            # Verify ARC4 was initialized with reversed hash
            mock_init_arc4.assert_called_once_with(mock_vin.prevout.hash[::-1])

    def test_quick_filter_src20_transaction_invalid(self):
        """Test quick_filter_src20_transaction with invalid transaction"""
        from index_core.transaction_utils import quick_filter_src20_transaction

        # Mock transaction context with regular P2PKH output
        mock_vout = Mock()
        mock_vout.scriptPubKey = b"\x76\xa9\x14..."  # P2PKH script

        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout]

        with patch("index_core.script.get_asm") as mock_get_asm, patch(
            "index_core.script.get_checkmultisig"
        ) as mock_get_multisig, patch("index_core.script.get_p2wsh") as mock_get_p2wsh:

            # Setup mocks for non-SRC20 transaction
            mock_get_asm.return_value = ["OP_DUP", "OP_HASH160", "pubkeyhash", "OP_EQUALVERIFY", "OP_CHECKSIG"]
            mock_get_multisig.return_value = ([], 0, 0)  # No multisig
            mock_get_p2wsh.return_value = []  # No P2WSH data

            result = quick_filter_src20_transaction(mock_ctx)

            assert result is False


class TestTransactionProcessingErrorHandling:
    """Test error handling in transaction processing functions"""

    def test_get_tx_info_decode_error(self):
        """Test get_tx_info handling DecodeError"""
        from exceptions import DecodeError
        from index_core.transaction_utils import get_tx_info

        test_tx_hex = "invalid_hex"

        with patch("index_core.transaction_utils.backend_instance") as mock_backend:
            # Mock backend to raise DecodeError
            mock_backend.deserialize.side_effect = DecodeError("Invalid transaction")

            with pytest.raises(DecodeError):
                get_tx_info(test_tx_hex)

    def test_decode_checkmultisig_data_length_error(self):
        """Test decode_checkmultisig with insufficient data length"""
        from index_core.exceptions import DecodeError
        from index_core.transaction_utils import decode_checkmultisig

        # Set up mock context with proper structure
        mock_vin = Mock()
        mock_vin.prevout.hash = b"\x12\x34" * 16
        mock_vout = Mock()
        mock_vout.scriptPubKey = b"test_script"
        mock_vout.nValue = 12345

        mock_ctx = Mock()
        mock_ctx.vin = [mock_vin]
        mock_ctx.vout = [mock_vout]

        # Create invalid decrypted chunk that will cause data length error
        invalid_chunk = b"\x00\x10" + config.PREFIX + b"short"  # Length says 16 but data is shorter

        with patch("index_core.arc4.init_arc4") as mock_init_arc4, patch("index_core.arc4.arc4_decrypt_chunk") as mock_decrypt:
            mock_init_arc4.return_value = "test_key"
            mock_decrypt.return_value = invalid_chunk

            with pytest.raises(DecodeError, match="invalid data length"):
                decode_checkmultisig(mock_ctx, b"encrypted_chunk")

    def test_decode_checkmultisig_no_inputs(self):
        """Test decode_checkmultisig with transaction that has no inputs"""
        from index_core.transaction_utils import decode_checkmultisig

        mock_ctx = Mock()
        mock_ctx.vin = []  # Empty inputs (like coinbase transaction)

        # This will raise IndexError when trying to access ctx.vin[0]
        with pytest.raises(IndexError):
            decode_checkmultisig(mock_ctx, b"test_chunk")

    def test_process_tx_exception_handling(self):
        """Test process_tx exception handling"""
        from index_core.transaction_utils import process_tx

        mock_db = Mock()
        test_tx_hash = "test_hash"
        raw_transactions = {test_tx_hash: "0100000001..."}  # Provide required tx_hex

        with patch("index_core.transaction_utils.list_tx") as mock_list_tx:
            # Mock list_tx to raise exception
            mock_list_tx.side_effect = Exception("Database error")

            result = process_tx(mock_db, test_tx_hash, 900001, [], raw_transactions)

            # Should return None values for all fields in TxResult (original behavior)
            assert result.source is None
            assert result.destination is None
            assert result.btc_amount is None


class TestTransactionProcessingEdgeCases:
    """Test edge cases in transaction processing functions"""

    def test_process_vout_with_non_multisig_script(self):
        """Test process_vout with non-multisig scripts"""
        from index_core.transaction_utils import process_vout

        # Create mock transaction context with scripts that don't end with OP_CHECKMULTISIG
        mock_vout1 = Mock()
        mock_vout1.scriptPubKey = b"\x76\xa9\x14"  # P2PKH script
        mock_vout1.nValue = 1000

        mock_vout2 = Mock()
        mock_vout2.scriptPubKey = b"\x00\x14"  # P2WPKH script
        mock_vout2.nValue = 500

        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout1, mock_vout2]

        with patch("index_core.script.get_asm") as mock_get_asm:
            # Return ASM that doesn't end with OP_CHECKMULTISIG
            mock_get_asm.side_effect = [
                ["OP_DUP", "OP_HASH160", "pubkeyhash", "OP_EQUALVERIFY", "OP_CHECKSIG"],
                ["OP_0", "hash"],
            ]

            result = process_vout(mock_ctx, 900001)

            # Original logic: only checks asm[-1] == "OP_CHECKMULTISIG"
            assert result.pubkeys_compiled == []
            assert result.keyburn is None  # Original behavior: None, not 0
            assert result.fee == 1500

    def test_process_vout_empty_vouts(self):
        """Test process_vout with transaction having no outputs"""
        from index_core.transaction_utils import process_vout

        mock_ctx = Mock()
        mock_ctx.vout = []

        result = process_vout(mock_ctx, 900001)

        # Should handle empty vouts gracefully - original behavior
        assert result.pubkeys_compiled == []
        assert result.keyburn is None  # Original behavior: None, not 0
        assert result.fee == 0

    def test_quick_filter_with_mock_gethash(self):
        """Test quick_filter_src20_transaction with mocked GetHash method"""
        from index_core.transaction_utils import quick_filter_src20_transaction
        import config

        # Create a mock transaction object with GetHash method
        mock_ctx = Mock()
        mock_ctx.GetHash.return_value = b"test_transaction_hash_12345678"
        
        # Create P2WSH data that includes the STAMP: prefix
        # The prefix is b"stamp:" according to config
        stamp_data = b"stamp:test_data_here"
        # Pad to 32 bytes if needed
        p2wsh_data = stamp_data.ljust(32, b'\x00')
        
        # Create a proper scriptPubKey mock with hex method
        mock_script_pubkey = Mock()
        # P2WSH pattern: 0x00 0x20 followed by 32 bytes of data containing "stamp:"
        mock_script_pubkey.hex.return_value = "0020" + p2wsh_data.hex()
        
        # Create vout with proper structure
        mock_vout = Mock()
        mock_vout.scriptPubKey = mock_script_pubkey
        mock_ctx.vout = [mock_vout]

        # Mock config.PREFIX to ensure it matches what we're testing
        with patch.object(config, 'PREFIX', b'stamp:'):
            # Should handle transaction with GetHash method
            result = quick_filter_src20_transaction(mock_ctx)
            assert result is True
            
            # Verify GetHash was called
            mock_ctx.GetHash.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
