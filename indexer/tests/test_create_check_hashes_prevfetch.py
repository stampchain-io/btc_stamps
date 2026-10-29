"""
Tests for the prev-block hash prefetch in ``create_check_hashes`` (issue #858).

The txlist_hash and messages_hash chains both need the previous block's hash,
which lives in the ``block_index - 1`` row. Previously each ``consensus_hash``
call re-SELECTed that row (twice per block). ``create_check_hashes`` now fetches
it once and passes the values in. The ledger_hash chain uses a different lookup
(last non-null ledger_hash) and is intentionally left to ``consensus_hash``.

Output-neutral: the previous hash passed to ``consensus_hash`` is exactly the
value it would otherwise have SELECTed itself.
"""

import unittest
from unittest.mock import Mock, patch

import index_core.block_validation as bv


class TestCreateCheckHashesPrevFetch(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.cursor = Mock()
        self.db.cursor.return_value = self.cursor

    @patch("index_core.block_validation.update_block_hashes")
    @patch("index_core.check.consensus_hash", return_value=("newhash", None))
    @patch("index_core.block_validation.config.BLOCK_FIRST", 779652)
    @patch("index_core.block_validation.config.BLOCK_FIELDS_POSITION", {"txlist_hash": 6, "messages_hash": 7})
    def test_prev_hashes_prefetched_once_and_passed_in(self, mock_ch, mock_ubh):
        """block_index-1 is SELECTed once; its txlist/messages hashes are passed
        to the respective consensus_hash calls; ledger is left untouched (None)."""
        prev_row = [None] * 10
        prev_row[6] = "PREV_TXLIST"
        prev_row[7] = "PREV_MSGS"
        # 1st fetchall -> current block row; 2nd -> block_index-1 row.
        self.cursor.fetchall.side_effect = [[tuple([None] * 10)], [tuple(prev_row)]]

        bv.create_check_hashes(self.db, 800001, [], "", [])

        # The prev-block row was fetched with block_index - 1.
        assert any(
            call.args[1] == (800000,) for call in self.cursor.execute.call_args_list if len(call.args) > 1
        ), "expected a SELECT for block_index - 1 (800000)"

        # previous_consensus_hash (positional arg index 3) per field.
        prev_by_field = {c.args[2]: c.args[3] for c in mock_ch.call_args_list}
        self.assertEqual(prev_by_field["txlist_hash"], "PREV_TXLIST")
        self.assertEqual(prev_by_field["messages_hash"], "PREV_MSGS")
        self.assertIsNone(prev_by_field["ledger_hash"])  # ledger path unchanged

        # consensus_hash is used off the persist path (issue #858 commit 1).
        for c in mock_ch.call_args_list:
            self.assertFalse(c.kwargs.get("persist", True))

    @patch("index_core.block_validation.update_block_hashes")
    @patch("index_core.check.consensus_hash", return_value=("newhash", None))
    @patch("index_core.block_validation.config.BLOCK_FIRST", 779652)
    @patch("index_core.block_validation.config.BLOCK_FIELDS_POSITION", {"txlist_hash": 6, "messages_hash": 7})
    def test_no_prefetch_on_first_block(self, mock_ch, mock_ubh):
        """At BLOCK_FIRST there is no block_index-1 to prefetch; no extra SELECT,
        and the previous hashes stay None (consensus_hash handles the seed)."""
        self.cursor.fetchall.side_effect = [[tuple([None] * 10)]]

        bv.create_check_hashes(self.db, 779652, [], "", [])

        # No SELECT for block_index - 1.
        assert not any(
            call.args[1] == (779651,) for call in self.cursor.execute.call_args_list if len(call.args) > 1
        ), "did not expect a prev-block SELECT on the first block"

        prev_by_field = {c.args[2]: c.args[3] for c in mock_ch.call_args_list}
        self.assertIsNone(prev_by_field["txlist_hash"])
        self.assertIsNone(prev_by_field["messages_hash"])

    @patch("index_core.block_validation.update_block_hashes")
    @patch("index_core.check.consensus_hash", return_value=("newhash", None))
    @patch("index_core.block_validation.config.BLOCK_FIRST", 779652)
    @patch("index_core.block_validation.config.BLOCK_FIELDS_POSITION", {"txlist_hash": 6, "messages_hash": 7})
    def test_missing_prev_row_leaves_previous_none(self, mock_ch, mock_ubh):
        """If block_index-1 is absent, previous hashes stay None so consensus_hash's
        existing missing-previous handling (reparse guidance) is preserved."""
        self.cursor.fetchall.side_effect = [[tuple([None] * 10)], []]  # no prev row

        bv.create_check_hashes(self.db, 800001, [], "", [])

        prev_by_field = {c.args[2]: c.args[3] for c in mock_ch.call_args_list}
        self.assertIsNone(prev_by_field["txlist_hash"])
        self.assertIsNone(prev_by_field["messages_hash"])


if __name__ == "__main__":
    unittest.main()
