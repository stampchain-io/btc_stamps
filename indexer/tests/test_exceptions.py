"""Tests for exceptions module."""

import unittest

from index_core.exceptions import (
    BlockAlreadyExistsError,
    BlockUpdateError,
    BTCOnlyError,
    CriticalBlockFetchError,
    DatabaseError,
    DatabaseInsertError,
    DataConversionError,
    DecodeError,
    InvalidInputDataError,
    LedgerMismatchError,
    MessageError,
    ParseTransactionError,
    PushDataDecodeError,
    SerializationError,
)


class TestExceptions(unittest.TestCase):
    """Test custom exception classes."""

    def test_database_error(self):
        """Test DatabaseError exception."""
        error = DatabaseError("DB error")
        self.assertEqual(str(error), "DB error")
        self.assertIsInstance(error, Exception)

    def test_parse_transaction_error(self):
        """Test ParseTransactionError exception."""
        error = ParseTransactionError("Parse failed")
        self.assertEqual(str(error), "Parse failed")
        self.assertIsInstance(error, Exception)

    def test_message_error(self):
        """Test MessageError exception."""
        error = MessageError("Message error")
        self.assertEqual(str(error), "Message error")
        self.assertIsInstance(error, Exception)

    def test_decode_error(self):
        """Test DecodeError exception."""
        error = DecodeError("Decode failed")
        self.assertEqual(str(error), "Decode failed")
        self.assertIsInstance(error, MessageError)

    def test_push_data_decode_error(self):
        """Test PushDataDecodeError exception."""
        error = PushDataDecodeError("Push data decode failed")
        self.assertEqual(str(error), "Push data decode failed")
        self.assertIsInstance(error, DecodeError)

    def test_btc_only_error(self):
        """Test BTCOnlyError exception."""
        decoded_tx = {"test": "data"}
        error = BTCOnlyError("BTC only", decodedTx=decoded_tx)
        self.assertEqual(str(error), "BTC only")
        self.assertEqual(error.decodedTx, decoded_tx)
        self.assertIsInstance(error, MessageError)

    def test_data_conversion_error(self):
        """Test DataConversionError exception."""
        error = DataConversionError()
        self.assertEqual(str(error), "Error occurred during data conversion")

        error_custom = DataConversionError("Custom message")
        self.assertEqual(str(error_custom), "Custom message")

    def test_invalid_input_data_error(self):
        """Test InvalidInputDataError exception."""
        error = InvalidInputDataError()
        self.assertEqual(str(error), "Invalid input data")

        error_custom = InvalidInputDataError("Custom invalid data")
        self.assertEqual(str(error_custom), "Custom invalid data")

    def test_serialization_error(self):
        """Test SerializationError exception."""
        error = SerializationError()
        self.assertEqual(str(error), "Error occurred during JSON serialization")

        error_custom = SerializationError("Serialization failed")
        self.assertEqual(str(error_custom), "Serialization failed")

    def test_block_already_exists_error(self):
        """Test BlockAlreadyExistsError exception."""
        error = BlockAlreadyExistsError("Block exists")
        self.assertEqual(str(error), "Block exists")
        self.assertIsInstance(error, Exception)

    def test_database_insert_error(self):
        """Test DatabaseInsertError exception."""
        error = DatabaseInsertError("Insert failed")
        self.assertEqual(str(error), "Insert failed")
        self.assertIsInstance(error, Exception)

    def test_block_update_error(self):
        """Test BlockUpdateError exception."""
        error = BlockUpdateError("Update failed")
        self.assertEqual(str(error), "Update failed")
        self.assertIsInstance(error, Exception)

    def test_ledger_mismatch_error(self):
        """Test LedgerMismatchError exception."""
        error = LedgerMismatchError(block_index=1000)
        self.assertEqual(str(error), "Ledger hash mismatch at block 1000")
        self.assertEqual(error.block_index, 1000)
        self.assertIsInstance(error, Exception)

    def test_critical_block_fetch_error(self):
        """Test CriticalBlockFetchError exception."""
        error = CriticalBlockFetchError(block_index=500, reason="Network error")
        self.assertEqual(str(error), "Critical fetch error for block 500: Network error")
        self.assertEqual(error.block_index, 500)
        self.assertEqual(error.reason, "Network error")
        self.assertIsInstance(error, Exception)

    def test_exception_inheritance(self):
        """Test exception inheritance relationships."""
        # Test MessageError hierarchy
        self.assertTrue(issubclass(DecodeError, MessageError))
        self.assertTrue(issubclass(PushDataDecodeError, DecodeError))
        self.assertTrue(issubclass(BTCOnlyError, MessageError))

        # All should inherit from Exception
        for exc_class in [
            DatabaseError,
            ParseTransactionError,
            MessageError,
            DataConversionError,
            InvalidInputDataError,
            SerializationError,
            BlockAlreadyExistsError,
            DatabaseInsertError,
            BlockUpdateError,
            LedgerMismatchError,
            CriticalBlockFetchError,
        ]:
            self.assertTrue(issubclass(exc_class, Exception))


if __name__ == "__main__":
    unittest.main()
