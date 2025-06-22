"""Tests for check module."""

import unittest
import warnings
from unittest.mock import MagicMock, Mock, patch

import config
from index_core.check import (
    CHECKPOINTS_MAINNET,
    CHECKPOINTS_REGTEST,
    CHECKPOINTS_TESTNET,
    ConsensusError,
    VersionError,
    VersionUpdateRequiredError,
    check_change,
    consensus_hash,
    software_version,
)


class TestCheckExceptions(unittest.TestCase):
    """Test exception classes in check module."""

    def test_consensus_error(self):
        """Test ConsensusError exception."""
        error = ConsensusError("Consensus failed")
        self.assertEqual(str(error), "Consensus failed")
        self.assertIsInstance(error, Exception)

    def test_version_error(self):
        """Test VersionError exception."""
        error = VersionError("Version mismatch")
        self.assertEqual(str(error), "Version mismatch")
        self.assertIsInstance(error, Exception)

    def test_version_update_required_error(self):
        """Test VersionUpdateRequiredError exception."""
        error = VersionUpdateRequiredError("Update required")
        self.assertEqual(str(error), "Update required")
        self.assertIsInstance(error, VersionError)
        self.assertIsInstance(error, Exception)


class TestSoftwareVersion(unittest.TestCase):
    """Test software_version function."""

    @patch("index_core.check.logger")
    @patch("index_core.check.config.VERSION_STRING", "1.2.3")
    def test_software_version_with_version(self, mock_logger):
        """Test software_version with version string."""
        software_version()
        mock_logger.info.assert_called_once_with("Software version: 1.2.3.")

    @patch("index_core.check.logger")
    @patch("index_core.check.config.VERSION_STRING", "")
    def test_software_version_empty(self, mock_logger):
        """Test software_version with empty version string."""
        software_version()
        mock_logger.info.assert_called_once_with("Software version: .")


class TestCheckChange(unittest.TestCase):
    """Test check_change function."""

    def setUp(self):
        """Set up test data."""
        self.protocol_change = {
            "minimum_version_major": 2,
            "minimum_version_minor": 0,
            "minimum_version_revision": 0,
            "block_index": 800000,
        }

    @patch("index_core.check.config.VERSION_MAJOR", 2)
    @patch("index_core.check.config.VERSION_MINOR", 1)
    @patch("index_core.check.config.VERSION_REVISION", 0)
    def test_check_change_pass(self):
        """Test check_change when version is sufficient."""
        # Should not raise any exception
        check_change(self.protocol_change, "Test change")

    @patch("index_core.check.config.VERSION_MAJOR", 1)
    @patch("index_core.check.config.VERSION_MINOR", 9)
    @patch("index_core.check.config.VERSION_REVISION", 9)
    @patch("index_core.check.util.CURRENT_BLOCK_INDEX", 800001)
    @patch("index_core.check.config.APP_NAME", "TestApp")
    @patch("index_core.check.config.VERSION_STRING", "1.9.9")
    def test_check_change_fail_current_block(
        self,
    ):
        """Test check_change when version is insufficient and past block."""
        with self.assertRaises(VersionUpdateRequiredError) as context:
            check_change(self.protocol_change, "Test change")

        self.assertIn("Your version of TestApp is v1.9.9", str(context.exception))
        self.assertIn("minimum version is v2.0.0", str(context.exception))

    @patch("index_core.check.config.VERSION_MAJOR", 1)
    @patch("index_core.check.config.VERSION_MINOR", 9)
    @patch("index_core.check.config.VERSION_REVISION", 9)
    @patch("index_core.check.util.CURRENT_BLOCK_INDEX", 799999)
    def test_check_change_warn_future_block(self):
        """Test check_change when version is insufficient but future block."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            check_change(self.protocol_change, "Test change")

            self.assertEqual(len(w), 1)
            self.assertIn("minimum version is v2.0.0", str(w[0].message))


class TestConsensusHash(unittest.TestCase):
    """Test consensus_hash function."""

    def setUp(self):
        """Set up test database mock."""
        self.db = Mock()
        self.cursor = Mock()
        self.db.cursor.return_value = self.cursor

    @patch("index_core.check.config.TESTNET", False)
    @patch("index_core.check.config.REGTEST", False)
    @patch("index_core.check.config.BLOCK_FIRST", 779652)
    @patch("index_core.check.config.BLOCK_FIELDS_POSITION", {"txlist_hash": 5})
    def test_consensus_hash_first_block(self):
        """Test consensus hash for first block."""
        # Mock empty database for new hash
        self.cursor.fetchall.return_value = []

        # Use the expected hash from checkpoint
        expected_hash = "f5277855a60219dfff0ea837e6835478cbbc32c3520cb1dc1f13c296594b3a05"

        with patch("index_core.check.util.dhash_string") as mock_dhash:
            mock_dhash.return_value = expected_hash

            calculated, found = consensus_hash(self.db, 779652, "txlist_hash", None, ["content1", "content2"])

            # Should hash the seed
            mock_dhash.assert_any_call(
                "Through our eyes, the universe is perceiving itself. Through our ears, the universe is listening to its harmonies."
            )

            # Should get the expected hash
            self.assertEqual(calculated, expected_hash)

    @patch("index_core.check.config.TESTNET", False)
    @patch("index_core.check.config.REGTEST", False)
    @patch("index_core.check.config.BLOCK_FIELDS_POSITION", {"txlist_hash": 5})
    def test_consensus_hash_with_checkpoint(self):
        """Test consensus hash validation against checkpoint."""
        block_index = 779700
        field = "txlist_hash"
        expected_hash = CHECKPOINTS_MAINNET[block_index][field]

        # Create a proper row tuple with the hash at the correct position
        row = [None] * 10  # Create list with enough positions
        row[5] = expected_hash  # Set txlist_hash at position 5
        self.cursor.fetchall.return_value = [tuple(row)]

        with patch("index_core.check.util.dhash_string") as mock_dhash:
            mock_dhash.return_value = expected_hash

            calculated, found = consensus_hash(self.db, block_index, field, "previous_hash", ["content"])

            self.assertEqual(calculated, expected_hash)
            self.assertEqual(found, expected_hash)

    @patch("index_core.check.config.TESTNET", False)
    @patch("index_core.check.config.REGTEST", False)
    @patch("index_core.check.config.BLOCK_FIELDS_POSITION", {"txlist_hash": 5})
    def test_consensus_hash_mismatch(self):
        """Test consensus hash mismatch raises error."""
        # Create a proper row tuple with different hash
        row = [None] * 10
        row[5] = "different_hash"
        self.cursor.fetchall.return_value = [tuple(row)]

        with patch("index_core.check.util.dhash_string") as mock_dhash:
            mock_dhash.return_value = "calculated_hash"

            with self.assertRaises(ConsensusError) as context:
                consensus_hash(self.db, 800000, "txlist_hash", "previous_hash", ["content"])

            # The error will be about inconsistent hash in database
            self.assertIn("Inconsistent txlist_hash for block 800000", str(context.exception))

    @patch("index_core.check.config.TESTNET", True)
    @patch("index_core.check.config.REGTEST", False)
    @patch("index_core.check.config.BLOCK_FIRST_TESTNET", 2979826)
    def test_consensus_hash_testnet(self):
        """Test consensus hash uses testnet checkpoints."""
        block_index = 2979827  # One block after BLOCK_FIRST_TESTNET
        field = "txlist_hash"

        # Mock empty database
        self.cursor.fetchall.return_value = []

        with patch("index_core.check.util.dhash_string") as mock_dhash:
            mock_dhash.return_value = "test_hash"

            calculated, found = consensus_hash(self.db, block_index, field, "previous_hash", ["content"])

            # Should update the database
            self.cursor.execute.assert_called_with(
                "UPDATE blocks SET txlist_hash = %s WHERE block_index = %s", ("test_hash", block_index)
            )

    @patch("index_core.check.config.CP_SRC20_GENESIS_BLOCK", 788041)
    def test_consensus_hash_ledger_src20_genesis(self):
        """Test consensus hash for SRC20 genesis block ledger."""
        expected_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

        # Mock empty database
        self.cursor.fetchall.return_value = []

        calculated, found = consensus_hash(self.db, config.CP_SRC20_GENESIS_BLOCK, "ledger_hash", None, "")

        self.assertEqual(calculated, expected_hash)

    def test_consensus_hash_ledger_empty_content(self):
        """Test consensus hash for ledger with empty content."""
        # Mock empty database
        self.cursor.fetchall.return_value = []

        calculated, found = consensus_hash(self.db, 800000, "ledger_hash", "previous_hash", "")

        self.assertEqual(calculated, "")


class TestCheckpoints(unittest.TestCase):
    """Test checkpoint data structures."""

    def test_mainnet_checkpoints_structure(self):
        """Test mainnet checkpoints have required fields."""
        self.assertIsInstance(CHECKPOINTS_MAINNET, dict)
        self.assertGreater(len(CHECKPOINTS_MAINNET), 0)

        for block_index, checkpoint in CHECKPOINTS_MAINNET.items():
            self.assertIsInstance(block_index, int)
            self.assertIn("ledger_hash", checkpoint)
            self.assertIn("txlist_hash", checkpoint)

    def test_testnet_checkpoints_structure(self):
        """Test testnet checkpoints have required fields."""
        self.assertIsInstance(CHECKPOINTS_TESTNET, dict)
        self.assertGreater(len(CHECKPOINTS_TESTNET), 0)

        for block_index, checkpoint in CHECKPOINTS_TESTNET.items():
            self.assertIsInstance(block_index, int)
            self.assertIn("ledger_hash", checkpoint)
            self.assertIn("txlist_hash", checkpoint)

    def test_regtest_checkpoints_structure(self):
        """Test regtest checkpoints have required fields."""
        self.assertIsInstance(CHECKPOINTS_REGTEST, dict)

        for block_index, checkpoint in CHECKPOINTS_REGTEST.items():
            self.assertIsInstance(block_index, int)
            self.assertIn("ledger_hash", checkpoint)
            self.assertIn("txlist_hash", checkpoint)


if __name__ == "__main__":
    unittest.main()
