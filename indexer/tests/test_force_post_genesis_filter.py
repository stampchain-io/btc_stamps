"""Unit tests for the reparse validator's ``_force_post_genesis_filter`` toggle (#774).

The context manager repurposes ``config.BTC_SRC20_GENESIS_BLOCK`` as a
filter-mode toggle so the in-memory reparse forces ``filter_block_transactions``
onto its post-genesis branch (decode every tx via the Rust parser) for every
block. These tests pin the two properties that make that safe:

  1. inside the context the threshold equals ``CP_STAMP_GENESIS_BLOCK`` (so the
     post-genesis branch is taken for every block_index), and
  2. the original value is ALWAYS restored — including on exceptions and when
     nested — so a transient bitcoind / CP-core error can't leak the mutated
     threshold into later blocks for the process lifetime.

The complementary CP-era invariant (no non-issuance tx in 779,652–793,067
produces protocol payload under this toggle) is guarded at integration level by
the Tier-3 reparse of the CP-era curated blocks — a leak surfaces there as a
consensus-hash mismatch.
"""

import pytest

import config
from index_core.reparse.validator import _force_post_genesis_filter


def test_toggle_lowers_threshold_to_cp_stamp_genesis():
    orig = config.BTC_SRC20_GENESIS_BLOCK
    # Precondition: the real SRC-20 genesis is above the stamp genesis, so the
    # toggle is a genuine change, not a no-op.
    assert orig != config.CP_STAMP_GENESIS_BLOCK
    with _force_post_genesis_filter():
        assert config.BTC_SRC20_GENESIS_BLOCK == config.CP_STAMP_GENESIS_BLOCK
    assert config.BTC_SRC20_GENESIS_BLOCK == orig


def test_toggle_restores_on_exception():
    """Restoration in finally is the 'can't leak into later blocks' guarantee."""
    orig = config.BTC_SRC20_GENESIS_BLOCK
    with pytest.raises(RuntimeError):
        with _force_post_genesis_filter():
            assert config.BTC_SRC20_GENESIS_BLOCK == config.CP_STAMP_GENESIS_BLOCK
            raise RuntimeError("simulated bitcoind/CP-core hiccup")
    assert config.BTC_SRC20_GENESIS_BLOCK == orig


def test_toggle_is_nesting_safe():
    orig = config.BTC_SRC20_GENESIS_BLOCK
    with _force_post_genesis_filter():
        with _force_post_genesis_filter():
            assert config.BTC_SRC20_GENESIS_BLOCK == config.CP_STAMP_GENESIS_BLOCK
        # inner exit restores to the value captured at inner enter (still toggled)
        assert config.BTC_SRC20_GENESIS_BLOCK == config.CP_STAMP_GENESIS_BLOCK
    assert config.BTC_SRC20_GENESIS_BLOCK == orig
