"""Tests for creator field fix: use CP issuer instead of source (fee-payer)."""

import json

import pytest

from index_core.models import StampData


def make_stamp_data(**overrides):
    """Helper to create a StampData with sensible defaults."""
    defaults = dict(
        tx_hash="abc123def456",
        source="fee_payer_address",
        prev_tx_hash="prev123",
        destination="artist_address",
        destination_nvalue=0,
        btc_amount=0,
        fee=1000,
        data=json.dumps(
            {
                "cpid": "A1234567890",
                "source": "fee_payer_address",
                "issuer": "artist_address",
                "quantity": 1,
                "divisible": False,
                "locked": True,
                "description": "stamp:base64data",
                "transfer": False,
                "status": "valid",
            }
        ),
        decoded_tx={},
        keyburn=1,
        tx_index=1,
        block_index=800000,
        block_time=1700000000,
        is_op_return=False,
        p2wsh_data=None,
    )
    defaults.update(overrides)
    return StampData(**defaults)


class TestCreatorFromIssuer:
    """Test that creator is set from CP issuer, not source."""

    def test_cp_stamp_creator_uses_issuer(self):
        """For CP stamps, creator should be the issuer (artist), not the source (fee-payer)."""
        stamp = make_stamp_data()
        stamp_dict = json.loads(stamp.data)
        stamp.update_stamp_data_rows_from_cp_asset(stamp_dict)
        stamp.update_stamp_hash_and_block_time()
        assert stamp.creator == "artist_address"
        assert stamp.creator != "fee_payer_address"

    def test_cp_stamp_same_source_and_issuer(self):
        """When source == issuer (self-minted), creator should be correct."""
        stamp = make_stamp_data(
            source="artist_address",
            data=json.dumps(
                {
                    "cpid": "A1234567890",
                    "source": "artist_address",
                    "issuer": "artist_address",
                    "quantity": 1,
                }
            ),
        )
        stamp_dict = json.loads(stamp.data)
        stamp.update_stamp_data_rows_from_cp_asset(stamp_dict)
        stamp.update_stamp_hash_and_block_time()
        assert stamp.creator == "artist_address"

    def test_non_cp_stamp_creator_uses_source(self):
        """For non-CP stamps (no issuer in data), creator should fall back to source."""
        stamp = make_stamp_data(
            data="raw_base64_data",
        )
        stamp.update_stamp_hash_and_block_time()
        assert stamp.creator == "fee_payer_address"

    def test_cp_stamp_data_without_issuer_key(self):
        """Edge case: CP data dict without issuer key falls back to source."""
        stamp = make_stamp_data(
            data=json.dumps({"cpid": "A1234567890", "quantity": 1}),
        )
        stamp_dict = json.loads(stamp.data)
        stamp.update_stamp_data_rows_from_cp_asset(stamp_dict)
        stamp.update_stamp_hash_and_block_time()
        assert stamp.creator == "fee_payer_address"

    def test_list_stamp_type_not_dict(self):
        """When stamp data is a list (JSON array), creator uses source."""
        stamp = make_stamp_data()
        stamp.update_stamp_data_rows_from_cp_asset([1, 2, 3])
        stamp.update_stamp_hash_and_block_time()
        assert stamp.creator == "fee_payer_address"

    def test_fairmint_uses_asset_issuer(self):
        """FAIRMINT stamps should use the asset issuer as creator."""
        stamp = make_stamp_data(
            source="minter_address",
            data=json.dumps(
                {
                    "cpid": "A9999999999",
                    "source": "minter_address",
                    "issuer": "original_deployer_address",
                    "event_type": "NEW_FAIRMINT",
                    "quantity": 100,
                }
            ),
        )
        stamp_dict = json.loads(stamp.data)
        stamp.update_stamp_data_rows_from_cp_asset(stamp_dict)
        stamp.update_stamp_hash_and_block_time()
        assert stamp.creator == "original_deployer_address"
        assert stamp.creator != "minter_address"

    def test_issuer_not_carried_across_instances(self):
        """Ensure _cp_issuer doesn't leak between different StampData instances."""
        stamp1 = make_stamp_data()
        stamp1_dict = json.loads(stamp1.data)
        stamp1.update_stamp_data_rows_from_cp_asset(stamp1_dict)
        stamp1.update_stamp_hash_and_block_time()
        assert stamp1.creator == "artist_address"

        stamp2 = make_stamp_data(
            source="another_source",
            data="raw_data_no_json",
        )
        stamp2.update_stamp_hash_and_block_time()
        assert stamp2.creator == "another_source"
        assert stamp2._cp_issuer is None
