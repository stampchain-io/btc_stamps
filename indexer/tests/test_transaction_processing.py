"""
Test cases for transaction processing functions that will be extracted from blocks.py

These tests ensure transaction processing functions work correctly before and after
refactoring to transaction_utils.py module.
"""

import os
import sys
import unittest.mock as mock
from unittest.mock import MagicMock, Mock, patch
from collections import namedtuple

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config


class TestTransactionProcessing:
    """Test cases for transaction processing functions from blocks.py"""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup method run before each test."""
        # Store original config values
        self.original_prefix = getattr(config, 'PREFIX', b'\x45\x4E\x44\x00')
        self.original_olga_block = getattr(config, 'BTC_SRC20_OLGA_BLOCK', 900000)
        
        # Set test config values
        config.PREFIX = b'\x45\x4E\x44\x00'
        config.BTC_SRC20_OLGA_BLOCK = 900000
        config.BTC_SRC101_OLGA_BLOCK = 900000

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
        mock_vout.scriptPubKey = b'\x51\x41\x04...'  # Mock script
        mock_vout.nValue = 1000
        
        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout]
        
        # Mock script analysis functions
        with patch('index_core.script.get_asm') as mock_get_asm, \
             patch('index_core.script.get_checkmultisig') as mock_get_multisig, \
             patch('index_core.script.get_p2wsh') as mock_get_p2wsh:
            
            # Setup mocks
            mock_get_asm.return_value = ['OP_1', 'pubkey1', 'pubkey2', 'OP_2', 'OP_CHECKMULTISIG']
            mock_get_multisig.return_value = (['pubkey1', 'pubkey2'], 1, 546)
            mock_get_p2wsh.return_value = []
            
            # Test the function
            result = process_vout(mock_ctx, 900001)
            
            # Verify results
            assert result.pubkeys_compiled == ['pubkey1', 'pubkey2']
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
        mock_vout.scriptPubKey = b'\x6a\x20...'  # OP_RETURN script
        mock_vout.nValue = 0
        
        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout]
        
        with patch('index_core.script.get_asm') as mock_get_asm, \
             patch('index_core.script.get_checkmultisig') as mock_get_multisig, \
             patch('index_core.script.get_p2wsh') as mock_get_p2wsh:
            
            # Setup for OP_RETURN detection
            mock_get_asm.return_value = ['OP_RETURN', 'data']
            mock_get_multisig.return_value = ([], 0, 0)
            mock_get_p2wsh.return_value = []
            
            result = process_vout(mock_ctx, 900001)
            
            assert result.is_op_return is True
            assert result.keyburn == 0
            assert result.fee == 0

    def test_process_vout_with_p2wsh_data_chunks(self):
        """Test process_vout collecting P2WSH data chunks"""
        from index_core.transaction_utils import process_vout
        
        # Create mock P2WSH outputs
        mock_vout1 = Mock()
        mock_vout1.scriptPubKey = b'\x00\x20...'
        mock_vout1.nValue = 546
        
        mock_vout2 = Mock()
        mock_vout2.scriptPubKey = b'\x00\x20...'
        mock_vout2.nValue = 546
        
        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout1, mock_vout2]
        
        with patch('index_core.script.get_asm') as mock_get_asm, \
             patch('index_core.script.get_checkmultisig') as mock_get_multisig, \
             patch('index_core.script.get_p2wsh') as mock_get_p2wsh:
            
            # Setup P2WSH data
            mock_get_asm.return_value = ['OP_0', 'hash']
            mock_get_multisig.return_value = ([], 0, 0)
            mock_get_p2wsh.side_effect = [['chunk1'], ['chunk2']]
            
            # Test with stamp issuance
            stamp_issuance = {'p2wsh_data_required': True}
            result = process_vout(mock_ctx, 900001, stamp_issuance)
            
            assert result.p2wsh_data_chunks == ['chunk1', 'chunk2']

    def test_decode_checkmultisig_valid_data(self):
        """Test decode_checkmultisig with valid encrypted data"""
        from index_core.transaction_utils import decode_checkmultisig
        
        # Create mock context
        mock_vin = Mock()
        mock_vin.prevout.hash = b'\x12\x34' * 16  # 32 bytes
        mock_ctx = Mock()
        mock_ctx.vin = [mock_vin]
        
        # Test data with PREFIX
        test_chunk = config.PREFIX + b'\x20' + b'A' * 32 + b'test_data'
        
        with patch('index_core.arc4.init_arc4') as mock_init_arc4, \
             patch('index_core.arc4.arc4_decrypt_chunk') as mock_decrypt, \
             patch('index_core.util.decode_address') as mock_decode_addr:
            
            # Setup mocks
            mock_init_arc4.return_value = 'test_key'
            mock_decrypt.return_value = b'decrypted_data'
            mock_decode_addr.return_value = 'test_address'
            
            destination, nvalue, data = decode_checkmultisig(mock_ctx, test_chunk)
            
            assert destination == 'test_address'
            assert nvalue == 0x41414141  # 'AAAA' as uint32
            assert data == b'decrypted_data'

    def test_decode_checkmultisig_invalid_prefix(self):
        """Test decode_checkmultisig with invalid prefix"""
        from index_core.transaction_utils import decode_checkmultisig
        from exceptions import DecodeError
        
        mock_ctx = Mock()
        test_chunk = b'\x00\x00\x00\x00' + b'invalid_data'
        
        with pytest.raises(DecodeError):
            decode_checkmultisig(mock_ctx, test_chunk)

    def test_get_tx_info_with_stamp_issuance(self):
        """Test get_tx_info with stamp issuance"""
        from index_core.transaction_utils import get_tx_info
        
        # Mock transaction hex
        test_tx_hex = '0100000001...'  # Simplified hex
        
        with patch('index_core.transaction_utils.backend_instance') as mock_backend, \
             patch('index_core.transaction_utils.process_vout') as mock_process_vout, \
             patch('index_core.util.CURRENT_BLOCK_INDEX', 900001), \
             patch('index_core.util.ib2h') as mock_ib2h:
            
            # Mock backend response
            mock_ctx = Mock()
            mock_ctx.vin = [Mock()]
            mock_ctx.vout = [Mock()]
            mock_ctx.hash = b'\x12\x34' * 16
            mock_backend.deserialize.return_value = mock_ctx
            
            # Mock process_vout result
            mock_vout_info = Mock()
            mock_vout_info.pubkeys_compiled = ['pubkey1']
            mock_vout_info.keyburn = 546
            mock_vout_info.is_op_return = False
            mock_vout_info.fee = 1000
            mock_vout_info.p2wsh_data_chunks = []
            mock_process_vout.return_value = mock_vout_info
            
            mock_ib2h.return_value = 'txhash'
            
            result = get_tx_info(test_tx_hex, block_index=900001, stamp_issuance=True)
            
            # Verify TransactionInfo structure
            assert hasattr(result, 'source')
            assert hasattr(result, 'destination')
            assert hasattr(result, 'btc_amount')
            assert hasattr(result, 'fee')
            assert hasattr(result, 'data')
            assert result.keyburn == 546
            
            mock_backend.deserialize.assert_called_once_with(test_tx_hex)

    def test_list_tx_valid_transaction(self):
        """Test list_tx with valid transaction"""
        from index_core.transaction_utils import list_tx
        
        mock_db = Mock()
        test_tx_hash = 'test_hash'
        test_tx_hex = '0100000001...'
        
        with patch('index_core.transaction_utils.get_tx_info') as mock_get_tx_info, \
             patch('index_core.util.CURRENT_BLOCK_INDEX', 900001):
            
            # Mock get_tx_info result
            mock_tx_info = Mock()
            mock_tx_info.source = 'source_address'
            mock_tx_info.destination = 'dest_address'
            mock_tx_info.btc_amount = 1000
            mock_tx_info.fee = 546
            mock_tx_info.data = b'test_data'
            mock_tx_info.keyburn = 0
            mock_get_tx_info.return_value = mock_tx_info
            
            result = list_tx(mock_db, 900001, test_tx_hash, test_tx_hex)
            
            # Verify result tuple structure
            assert len(result) == 11
            assert result[0] == 'source_address'  # source
            assert result[1] == 'dest_address'    # destination
            assert result[2] == 1000             # btc_amount
            assert result[3] == 546              # fee
            assert result[4] == b'test_data'     # data

    def test_list_tx_no_data_transaction(self):
        """Test list_tx with transaction that has no relevant data"""
        from index_core.transaction_utils import list_tx
        
        mock_db = Mock()
        test_tx_hash = 'test_hash'
        test_tx_hex = '0100000001...'
        
        with patch('index_core.transaction_utils.get_tx_info') as mock_get_tx_info, \
             patch('index_core.util.CURRENT_BLOCK_INDEX', 900001):
            
            # Mock get_tx_info to return None (no relevant data)
            mock_get_tx_info.return_value = None
            
            result = list(list_tx(mock_db, 900001, test_tx_hash, test_tx_hex))
            
            # Should return generator of None values
            assert all(item is None for item in result)

    def test_process_tx_with_matching_issuance(self):
        """Test process_tx with matching stamp issuance"""
        from index_core.transaction_utils import process_tx
        
        mock_db = Mock()
        test_tx_hash = 'test_hash'
        test_block_index = 900001
        
        # Mock stamp issuance data
        stamp_issuances = [
            {'tx_hash': 'other_hash', 'cpid': 'A1234'},
            {'tx_hash': 'test_hash', 'cpid': 'A5678'},
        ]
        raw_transactions = {test_tx_hash: '0100000001...'}
        
        with patch('index_core.transaction_utils.list_tx') as mock_list_tx, \
             patch('index_core.fetch_utils.find_issuance_by_tx_hash') as mock_find_issuance:
            
            # Mock list_tx result
            mock_list_tx.return_value = ('source', 'dest', 1000, 546, b'data', 0, 'hash', 'op', 0, False, 'txhash')
            
            # Mock find_issuance_by_tx_hash
            mock_find_issuance.return_value = {'cpid': 'A5678'}
            
            result = process_tx(mock_db, test_tx_hash, test_block_index, stamp_issuances, raw_transactions)
            
            # Verify TxResult structure
            assert hasattr(result, 'source')
            assert hasattr(result, 'destination') 
            assert hasattr(result, 'btc_amount')
            assert hasattr(result, 'fee')
            assert hasattr(result, 'data')
            assert result.source == 'source'
            assert result.destination == 'dest'

    def test_quick_filter_src20_transaction_valid_p2wsh(self):
        """Test quick_filter_src20_transaction with valid P2WSH transaction"""
        from index_core.transaction_utils import quick_filter_src20_transaction
        
        # Mock transaction context with P2WSH output
        mock_vout = Mock()
        mock_vout.scriptPubKey = b'\x00\x20' + b'\x12\x34' * 16  # P2WSH script
        
        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout]
        
        with patch('index_core.script.get_asm') as mock_get_asm, \
             patch('index_core.script.get_p2wsh') as mock_get_p2wsh:
            
            mock_get_asm.return_value = ['OP_0', 'hash']
            mock_get_p2wsh.return_value = ['data_chunk']
            
            result = quick_filter_src20_transaction(mock_ctx)
            
            assert result is True

    def test_quick_filter_src20_transaction_valid_multisig(self):
        """Test quick_filter_src20_transaction with valid multisig transaction"""
        from index_core.transaction_utils import quick_filter_src20_transaction
        
        # Mock transaction context with multisig output
        mock_vout = Mock()
        mock_vout.scriptPubKey = b'\x51\x41\x04...'  # Multisig script
        
        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout]
        
        with patch('index_core.script.get_asm') as mock_get_asm, \
             patch('index_core.script.get_checkmultisig') as mock_get_multisig, \
             patch('index_core.script.get_p2wsh') as mock_get_p2wsh, \
             patch('index_core.arc4.init_arc4') as mock_init_arc4, \
             patch('index_core.arc4.arc4_decrypt_chunk') as mock_decrypt:
            
            # Setup mocks for valid multisig with keyburn
            mock_get_asm.return_value = ['OP_1', 'pubkey1', 'OP_1', 'OP_CHECKMULTISIG']
            mock_get_multisig.return_value = (['pubkey1'], 1, 546)  # Has keyburn
            mock_get_p2wsh.return_value = []
            
            # Mock successful decryption with PREFIX
            mock_init_arc4.return_value = 'test_key'
            mock_decrypt.return_value = config.PREFIX + b'test_data'
            
            result = quick_filter_src20_transaction(mock_ctx)
            
            assert result is True

    def test_quick_filter_src20_transaction_invalid(self):
        """Test quick_filter_src20_transaction with invalid transaction"""
        from index_core.transaction_utils import quick_filter_src20_transaction
        
        # Mock transaction context with regular P2PKH output
        mock_vout = Mock()
        mock_vout.scriptPubKey = b'\x76\xa9\x14...'  # P2PKH script
        
        mock_ctx = Mock()
        mock_ctx.vout = [mock_vout]
        
        with patch('index_core.script.get_asm') as mock_get_asm, \
             patch('index_core.script.get_checkmultisig') as mock_get_multisig, \
             patch('index_core.script.get_p2wsh') as mock_get_p2wsh:
            
            # Setup mocks for non-SRC20 transaction
            mock_get_asm.return_value = ['OP_DUP', 'OP_HASH160', 'pubkeyhash', 'OP_EQUALVERIFY', 'OP_CHECKSIG']
            mock_get_multisig.return_value = ([], 0, 0)  # No multisig
            mock_get_p2wsh.return_value = []  # No P2WSH data
            
            result = quick_filter_src20_transaction(mock_ctx)
            
            assert result is False


class TestTransactionProcessingErrorHandling:
    """Test error handling in transaction processing functions"""

    def test_get_tx_info_decode_error(self):
        """Test get_tx_info handling DecodeError"""
        from index_core.transaction_utils import get_tx_info
        from exceptions import DecodeError
        
        test_tx_hex = 'invalid_hex'
        
        with patch('index_core.transaction_utils.backend_instance') as mock_backend:
            # Mock backend to raise DecodeError
            mock_backend.deserialize.side_effect = DecodeError("Invalid transaction")
            
            with pytest.raises(DecodeError):
                get_tx_info(test_tx_hex)

    def test_decode_checkmultisig_data_length_error(self):
        """Test decode_checkmultisig with insufficient data length"""
        from index_core.transaction_utils import decode_checkmultisig
        from exceptions import DecodeError
        
        mock_ctx = Mock()
        # Test chunk with valid prefix but insufficient length
        test_chunk = config.PREFIX + b'\x20'  # Missing address and data
        
        with pytest.raises(DecodeError):
            decode_checkmultisig(mock_ctx, test_chunk)

    def test_process_tx_exception_handling(self):
        """Test process_tx exception handling"""
        from index_core.transaction_utils import process_tx
        
        mock_db = Mock()
        test_tx_hash = 'test_hash'
        
        with patch('index_core.transaction_utils.list_tx') as mock_list_tx:
            # Mock list_tx to raise exception
            mock_list_tx.side_effect = Exception("Database error")
            
            result = process_tx(mock_db, test_tx_hash, 900001, [], {})
            
            # Should return None values for all fields in TxResult
            assert result.source is None
            assert result.destination is None
            assert result.btc_amount is None


class TestTransactionProcessingEdgeCases:
    """Test edge cases in transaction processing functions"""

    def test_process_vout_empty_vouts(self):
        """Test process_vout with transaction having no outputs"""
        from index_core.transaction_utils import process_vout
        
        mock_ctx = Mock()
        mock_ctx.vout = []
        
        result = process_vout(mock_ctx, 900001)
        
        # Should handle empty vouts gracefully
        assert result.pubkeys_compiled == []
        assert result.keyburn == 0
        assert result.fee == 0

    def test_quick_filter_with_dict_context(self):
        """Test quick_filter_src20_transaction with dict context instead of CTransaction"""
        from index_core.transaction_utils import quick_filter_src20_transaction
        
        # Test with dict-style context (as might come from different sources)
        dict_ctx = {
            'vout': [
                {'scriptPubKey': b'\x00\x20' + b'\x12\x34' * 16}
            ]
        }
        
        with patch('index_core.script.get_asm') as mock_get_asm, \
             patch('index_core.script.get_p2wsh') as mock_get_p2wsh:
            
            mock_get_asm.return_value = ['OP_0', 'hash']
            mock_get_p2wsh.return_value = ['data_chunk']
            
            # Should handle dict context
            result = quick_filter_src20_transaction(dict_ctx)
            assert result is True


if __name__ == "__main__":
    pytest.main([__file__])