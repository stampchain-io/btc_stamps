"""
Tests for the ``persist`` parameter of ``check.consensus_hash`` (issue #858).

``create_check_hashes`` writes txlist/ledger/messages together via
``update_block_hashes`` immediately after the three ``consensus_hash`` calls, so
the per-field ``UPDATE`` inside each call is redundant on that path. ``persist``
(default ``True``, preserving behavior for every other caller) lets that path
opt out of the redundant write. These tests pin the behavior:

  * ``persist=False`` on a fresh block issues NO ``UPDATE`` (no DB write);
  * ``persist=True`` (default) still issues the ``UPDATE`` (unchanged for other
    callers, e.g. ``reparse/snapshot.py`` and the existing test suite);
  * ``persist`` never affects the verify-against-existing branch (the real
    consensus check on reprocessing).

The calculated hash is identical regardless of ``persist`` -> output-neutral.
"""

import unittest
from unittest.mock import Mock, patch

from index_core.check import consensus_hash


class TestConsensusHashPersist(unittest.TestCase):
    """Persist flag gates only the per-field UPDATE, not the hash or the verify."""

    def setUp(self):
        self.db = Mock()
        self.cursor = Mock()
        self.db.cursor.return_value = self.cursor

    @patch("index_core.check.CHECKPOINTS_MAINNET", {})
    @patch("index_core.check.config.TESTNET", False)
    @patch("index_core.check.config.REGTEST", False)
    @patch("index_core.check.config.BLOCK_FIRST", 779652)
    @patch("index_core.check.config.BLOCK_FIELDS_POSITION", {"txlist_hash": 6, "messages_hash": 7})
    def test_persist_false_skips_update(self):
        """Fresh block, persist=False -> no UPDATE executed.

        block_row is passed in (no block-row SELECT) and a previous hash is
        passed (no prev-hash SELECT), so the ONLY DB op that could fire is the
        per-field UPDATE. Asserting execute() was never called proves it is
        skipped.
        """
        block_row = [None] * 10  # txlist_hash (pos 6) is None -> found_hash None -> save branch
        with patch("index_core.check.util.dhash_string", return_value="calc_hash"):
            calculated, found = consensus_hash(
                self.db, 800001, "txlist_hash", "prev_hash", "content", block_row=tuple(block_row), persist=False
            )

        self.assertEqual(calculated, "calc_hash")
        self.assertIsNone(found)
        self.cursor.execute.assert_not_called()

    @patch("index_core.check.CHECKPOINTS_MAINNET", {})
    @patch("index_core.check.config.TESTNET", False)
    @patch("index_core.check.config.REGTEST", False)
    @patch("index_core.check.config.BLOCK_FIRST", 779652)
    @patch("index_core.check.config.BLOCK_FIELDS_POSITION", {"txlist_hash": 6, "messages_hash": 7})
    def test_persist_true_still_updates(self):
        """Fresh block, persist=True (default) -> UPDATE executed (unchanged)."""
        block_row = [None] * 10
        with patch("index_core.check.util.dhash_string", return_value="calc_hash"):
            calculated, _ = consensus_hash(
                self.db, 800001, "txlist_hash", "prev_hash", "content", block_row=tuple(block_row), persist=True
            )

        self.assertEqual(calculated, "calc_hash")
        self.cursor.execute.assert_called_once()
        sql = self.cursor.execute.call_args[0][0]
        self.assertIn("UPDATE blocks SET", sql)
        self.assertIn("txlist_hash", sql)

    @patch("index_core.check.CHECKPOINTS_MAINNET", {})
    @patch("index_core.check.config.TESTNET", False)
    @patch("index_core.check.config.REGTEST", False)
    @patch("index_core.check.config.BLOCK_FIRST", 779652)
    @patch("index_core.check.config.BLOCK_FIELDS_POSITION", {"txlist_hash": 6, "messages_hash": 7})
    def test_persist_defaults_to_true(self):
        """Omitting persist preserves the historical UPDATE behavior."""
        block_row = [None] * 10
        with patch("index_core.check.util.dhash_string", return_value="calc_hash"):
            consensus_hash(self.db, 800001, "txlist_hash", "prev_hash", "content", block_row=tuple(block_row))
        self.cursor.execute.assert_called_once()
        self.assertIn("UPDATE blocks SET", self.cursor.execute.call_args[0][0])

    @patch("index_core.check.CHECKPOINTS_MAINNET", {})
    @patch("index_core.check.config.TESTNET", False)
    @patch("index_core.check.config.REGTEST", False)
    @patch("index_core.check.config.BLOCK_FIRST", 779652)
    @patch("index_core.check.config.BLOCK_FIELDS_POSITION", {"txlist_hash": 6, "messages_hash": 7})
    def test_persist_false_messages_hash_skips_update(self):
        """messages_hash always takes the save branch; persist=False still skips it."""
        block_row = [None] * 10
        with patch("index_core.check.util.dhash_string", return_value="calc_hash"):
            consensus_hash(self.db, 800001, "messages_hash", "prev_hash", "content", block_row=tuple(block_row), persist=False)
        self.cursor.execute.assert_not_called()

    @patch("index_core.check.handle_consensus_error")
    @patch("index_core.check.CHECKPOINTS_MAINNET", {})
    @patch("index_core.check.config.TESTNET", False)
    @patch("index_core.check.config.REGTEST", False)
    @patch("index_core.check.config.BLOCK_FIRST", 779652)
    @patch("index_core.check.config.BLOCK_FIELDS_POSITION", {"txlist_hash": 6, "messages_hash": 7})
    def test_persist_false_preserves_verify_branch(self, mock_err):
        """persist only gates the save branch: a matching existing hash still
        verifies clean (no UPDATE, no error) even with persist=False."""
        block_row = [None] * 10
        block_row[6] = "calc_hash"  # existing txlist_hash matches calculated -> verify path
        with patch("index_core.check.util.dhash_string", return_value="calc_hash"):
            _, found = consensus_hash(
                self.db, 800001, "txlist_hash", "prev_hash", "content", block_row=tuple(block_row), persist=False
            )
        self.assertEqual(found, "calc_hash")
        mock_err.assert_not_called()
        self.cursor.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
