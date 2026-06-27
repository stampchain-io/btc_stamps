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

Other tests in the suite both mutate ``config.BTC_SRC20_GENESIS_BLOCK`` and
``importlib.reload(config)`` (replacing the ``config`` object in
``sys.modules``). The context manager does ``import config`` at call time, so to
observe the SAME module object — not a stale one captured at import — each test
resolves ``config`` inside the function body and pins the value via
``monkeypatch`` (auto-restored at teardown). These tests therefore neither
depend on nor pollute that global.

The complementary CP-era invariant (no non-issuance tx in 779,652–793,067
produces protocol payload under this toggle) is guarded at integration level by
the Tier-3 reparse of the CP-era curated blocks — a leak surfaces there as a
consensus-hash mismatch.
"""

import pytest

from index_core.reparse.validator import _force_post_genesis_filter

# An arbitrary block height distinct from CP_STAMP_GENESIS_BLOCK, so the toggle
# is a genuine change rather than a no-op.
_SENTINEL = 808_080


def test_toggle_lowers_threshold_to_cp_stamp_genesis(monkeypatch):
    import config  # resolve the same object the context manager imports at call time

    monkeypatch.setattr(config, "BTC_SRC20_GENESIS_BLOCK", _SENTINEL)
    assert _SENTINEL != config.CP_STAMP_GENESIS_BLOCK
    with _force_post_genesis_filter():
        assert config.BTC_SRC20_GENESIS_BLOCK == config.CP_STAMP_GENESIS_BLOCK
    assert config.BTC_SRC20_GENESIS_BLOCK == _SENTINEL


def test_toggle_restores_on_exception(monkeypatch):
    """Restoration in finally is the 'can't leak into later blocks' guarantee."""
    import config

    monkeypatch.setattr(config, "BTC_SRC20_GENESIS_BLOCK", _SENTINEL)
    with pytest.raises(RuntimeError):
        with _force_post_genesis_filter():
            assert config.BTC_SRC20_GENESIS_BLOCK == config.CP_STAMP_GENESIS_BLOCK
            raise RuntimeError("simulated bitcoind/CP-core hiccup")
    assert config.BTC_SRC20_GENESIS_BLOCK == _SENTINEL


def test_toggle_is_nesting_safe(monkeypatch):
    import config

    monkeypatch.setattr(config, "BTC_SRC20_GENESIS_BLOCK", _SENTINEL)
    with _force_post_genesis_filter():
        with _force_post_genesis_filter():
            assert config.BTC_SRC20_GENESIS_BLOCK == config.CP_STAMP_GENESIS_BLOCK
        # inner exit restores to the value captured at inner enter (still toggled)
        assert config.BTC_SRC20_GENESIS_BLOCK == config.CP_STAMP_GENESIS_BLOCK
    assert config.BTC_SRC20_GENESIS_BLOCK == _SENTINEL
