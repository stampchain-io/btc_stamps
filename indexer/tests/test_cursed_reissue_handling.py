# pytest unit tests for re-issuance handling of duplicate CPIDs
# Located in indexer/tests/test_cursed_reissue_handling.py

from unittest.mock import Mock, patch

import pytest

import index_core.database as database
from index_core.stamp import StampData, StampProcessor


@pytest.mark.unit
def test_check_reissue_in_block_detects_duplicate_cursed():
    """When a cursed stamp with the same CPID appears twice in the same block, the second
    appearance must be treated as a re-issue (duplicate) and therefore skipped.
    """
    cpid = "A1234567890123"
    # First appearance (valid)
    valid_stamps_in_block = [
        {"cpid": cpid, "is_btc_stamp": False, "is_cursed": True},
    ]

    # Second appearance should be detected as re-issue
    assert database.check_reissue_in_block(valid_stamps_in_block, cpid) is True


@pytest.mark.unit
def test_check_reissue_in_block_detects_duplicate_positive():
    """Duplicate positive-number stamp CPID should also be flagged as re-issue."""
    cpid = "A9876543210987"
    valid_stamps_in_block = [
        {"cpid": cpid, "is_btc_stamp": True},
    ]

    assert database.check_reissue_in_block(valid_stamps_in_block, cpid) is True


@pytest.mark.unit
@patch("index_core.stamp.get_next_stamp_number", return_value=1)
@patch("index_core.stamp.check_reissue", return_value=False)
@patch.object(StampData, "process_and_store_stamp_data", autospec=True)
def test_stamp_processor_creates_validstamp_for_cursed_with_A_prefix(
    mock_process_and_store, mock_check_reissue, mock_next_stamp
):
    """Ensure that cursed stamps whose CPID starts with 'A' now generate a ValidStamp entry
    (regression test for the previous filter that skipped such cases)."""

    # Simulate successful internal processing by setting the necessary attributes
    def _fake_process(self, *_, **__):  # noqa: D401,E501  pylint: disable=unused-argument
        self.is_cursed = True
        self.is_btc_stamp = False
        self.cpid = "A1122334455667"  # starts with A – previously excluded
        self.is_valid_base64 = True
        self.stamp_base64 = ""  # minimal valid base64
        self.src_data = ""
        self.pval_src20 = False
        self.pval_src101 = False
        return True

    mock_process_and_store.side_effect = _fake_process

    db = Mock()
    processor = StampProcessor(db, valid_stamps_in_block=[])

    stamp_data = StampData(
        tx_hash="txhash",
        source="addr1",
        prev_tx_hash="",
        destination="addr2",
        destination_nvalue=0,
        btc_amount=0,
        fee=0,
        data="{}",
        decoded_tx={},
        keyburn=0,
        tx_index=0,
        block_index=800000,
        block_time=0,
        is_op_return=True,
        p2wsh_data=b"",
    )

    stamp_results, _, valid_stamp, _ = processor.process_stamp(stamp_data)

    assert stamp_results is True
    assert valid_stamp is not None
    assert valid_stamp["cpid"] == "A1122334455667"
    assert valid_stamp["is_cursed"] is True


@pytest.mark.unit
@patch("index_core.stamp.get_next_stamp_number", return_value=100)
@patch("index_core.stamp.check_reissue", return_value=False)
@patch.object(StampData, "process_and_store_stamp_data", autospec=True)
def test_stamp_processor_creates_validstamp_for_positive_btc_stamp(
    mock_process_and_store, mock_check_reissue, mock_next_stamp
):
    """Ensure that positive BTC stamps generate a ValidStamp entry for reissue tracking."""

    # Simulate successful internal processing by setting the necessary attributes
    def _fake_process(self, *_, **__):  # noqa: D401,E501  pylint: disable=unused-argument
        self.is_cursed = False
        self.is_btc_stamp = True
        self.cpid = "A9988776655443"  # Standard Counterparty asset ID
        self.is_valid_base64 = True
        self.stamp_base64 = ""
        self.src_data = ""
        self.pval_src20 = False
        self.pval_src101 = False
        return True

    mock_process_and_store.side_effect = _fake_process

    db = Mock()
    processor = StampProcessor(db, valid_stamps_in_block=[])

    stamp_data = StampData(
        tx_hash="txhash_positive",
        source="addr1",
        prev_tx_hash="",
        destination="addr2",
        destination_nvalue=0,
        btc_amount=0,
        fee=0,
        data="{}",
        decoded_tx={},
        keyburn=0,
        tx_index=0,
        block_index=800000,
        block_time=0,
        is_op_return=True,
        p2wsh_data=b"",
    )

    stamp_results, _, valid_stamp, _ = processor.process_stamp(stamp_data)

    assert stamp_results is True
    assert valid_stamp is not None
    assert valid_stamp["cpid"] == "A9988776655443"
    assert valid_stamp["is_btc_stamp"] is True
    assert valid_stamp["is_cursed"] is False


@pytest.mark.unit
def test_check_reissue_detects_cursed_and_positive_equally():
    """Test that reissue detection works equally for cursed and positive stamps."""
    cpid_shared = "A1111222233334"
    
    # Block with both cursed and positive stamps using the same CPID
    valid_stamps_in_block = [
        {"cpid": cpid_shared, "is_btc_stamp": True},  # positive stamp
        {"cpid": cpid_shared, "is_btc_stamp": False, "is_cursed": True},  # cursed stamp
    ]

    # Both should be detected as reissues
    assert database.check_reissue_in_block(valid_stamps_in_block, cpid_shared) is True
