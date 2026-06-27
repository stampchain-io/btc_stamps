"""Unit tests for issue #756 item 3 — skip the Counterparty (CP) API fetch for
blocks that carry NO Counterparty data.

The skip is gated by ``config.CP_SKIP_NO_COUNTERPARTY_BLOCKS`` (default False) and
consumes #754's over-approximating ``TransactionInfo.has_counterparty_data``
signal via ``block_validation.block_has_counterparty_data``. These tests assert:

  * Flag OFF (default) -> the CP fetch is ALWAYS called (behavior preserved).
  * Flag ON + a block whose parsed txs are all CP-free -> the CP fetch is NOT
    called and the substituted ``block_data`` equals the empty-fetch shape.
  * Flag ON + a block with >= 1 CP-bearing tx -> the CP fetch IS called.
  * The predicate's detection truth is wired correctly to the real Rust parser
    (``any`` over real CP-era / native stamp fixtures).

DB-free and network-free: bitcoind RPC and the CP fetch are mocked; the
detection truth test uses the built ``btc_stamps_parser`` extension and the
committed transaction-cache fixtures.
"""

import json
import os
from unittest.mock import MagicMock

import pytest

import config
from index_core import block_validation

FastTransactionParser = pytest.importorskip("btc_stamps_parser").FastTransactionParser

_TRANSACTION_CACHE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "transaction_cache")

# Classic CP-era multisig stamp (a genuine CNTRPRTY issuance) -> has CP data.
_CP_TXID = "0321905ca9053a5b8313be9524a2af146196982a479573e9a324e8b929231730"  # block 789352
# Native keyburn SRC-20 stamp (parsed from Bitcoin, never via the CP API) -> no CP data.
_NATIVE_TXID = "049d1544e94c14deece7a468855ca9bff7c867476b3f4cba8c075000ed93babe"  # block 797973


def _load_tx_hex(txid: str) -> str:
    with open(os.path.join(_TRANSACTION_CACHE_DIR, f"{txid}.json")) as fh:
        data = json.load(fh)
    tx_hex = data.get("hex")
    assert tx_hex, f"fixture {txid} has no hex"
    return tx_hex


@pytest.fixture
def patch_fetch(monkeypatch):
    """Patch ``fetch_xcp_blocks_concurrent`` (imported lazily inside the wrapper)
    so we can assert whether / how the real CP fetch is invoked."""
    fetch = MagicMock(
        side_effect=lambda start, end, progress_indicator=False: {
            idx: {"block_index": idx, "xcp_block_hash": "deadbeef", "transactions": [{"tx_hash": "a"}], "issuances": []}
            for idx in range(start, end + 1)
        }
    )
    monkeypatch.setattr("index_core.fetch_utils.fetch_xcp_blocks_concurrent", fetch)
    return fetch


# ---------------------------------------------------------------------------
# Wrapper: fetch_cp_blocks_skipping_empty
# ---------------------------------------------------------------------------


def test_flag_off_always_fetches(monkeypatch, patch_fetch):
    """Flag OFF (default) -> pass-through; CP fetch always called, predicate never consulted."""
    monkeypatch.setattr(config, "CP_SKIP_NO_COUNTERPARTY_BLOCKS", False)
    # Predicate must NOT be consulted when the flag is off.
    monkeypatch.setattr(
        block_validation,
        "block_has_counterparty_data",
        MagicMock(side_effect=AssertionError("predicate must not run when flag is off")),
    )

    result = block_validation.fetch_cp_blocks_skipping_empty(100, 102)

    patch_fetch.assert_called_once_with(100, 102, progress_indicator=False)
    assert set(result.keys()) == {100, 101, 102}


def test_flag_on_all_cp_free_skips_fetch(monkeypatch, patch_fetch):
    """Flag ON + every block CP-free -> CP fetch NOT called; empty-fetch shape substituted."""
    monkeypatch.setattr(config, "CP_SKIP_NO_COUNTERPARTY_BLOCKS", True)
    monkeypatch.setattr(block_validation, "block_has_counterparty_data", MagicMock(return_value=False))

    result = block_validation.fetch_cp_blocks_skipping_empty(100, 102)

    patch_fetch.assert_not_called()
    assert result == {
        100: {"block_index": 100, "xcp_block_hash": None, "transactions": [], "issuances": []},
        101: {"block_index": 101, "xcp_block_hash": None, "transactions": [], "issuances": []},
        102: {"block_index": 102, "xcp_block_hash": None, "transactions": [], "issuances": []},
    }


def test_flag_on_cp_bearing_block_is_fetched(monkeypatch, patch_fetch):
    """Flag ON + one CP-bearing block -> only that block hits the CP API; the rest are empty."""
    monkeypatch.setattr(config, "CP_SKIP_NO_COUNTERPARTY_BLOCKS", True)
    # Only block 101 carries Counterparty data.
    monkeypatch.setattr(
        block_validation,
        "block_has_counterparty_data",
        MagicMock(side_effect=lambda idx: idx == 101),
    )

    result = block_validation.fetch_cp_blocks_skipping_empty(100, 102)

    # The CP API is called exactly once, for the contiguous run covering block 101.
    patch_fetch.assert_called_once_with(101, 101, progress_indicator=False)
    assert result[100] == {"block_index": 100, "xcp_block_hash": None, "transactions": [], "issuances": []}
    assert result[102] == {"block_index": 102, "xcp_block_hash": None, "transactions": [], "issuances": []}
    # Block 101 is the real fetched payload, not the empty shape.
    assert result[101]["transactions"] == [{"tx_hash": "a"}]


def test_flag_on_all_cp_bearing_fetches_full_range(monkeypatch, patch_fetch):
    """Flag ON + every block CP-bearing -> single fetch over the whole range (no skips)."""
    monkeypatch.setattr(config, "CP_SKIP_NO_COUNTERPARTY_BLOCKS", True)
    monkeypatch.setattr(block_validation, "block_has_counterparty_data", MagicMock(return_value=True))

    result = block_validation.fetch_cp_blocks_skipping_empty(100, 102)

    patch_fetch.assert_called_once_with(100, 102, progress_indicator=False)
    assert set(result.keys()) == {100, 101, 102}


# ---------------------------------------------------------------------------
# Predicate plumbing: block_has_counterparty_data
# ---------------------------------------------------------------------------


def test_predicate_plumbs_through_to_parser(monkeypatch):
    """block_has_counterparty_data fetches the raw block, parses ALL txs, and
    returns any(has_counterparty_data) — exercised with a stub parser/backend."""

    class _StubInfo:
        def __init__(self, has_cp):
            self.has_counterparty_data = has_cp

    class _StubRawParser:
        def __init__(self, flags):
            # flags: ordered list of has_counterparty_data values per tx hex
            self._flags = flags

        def parse_block(self, block_hex):
            raw = {f"tx{i}": f"hex{i}" for i in range(len(self._flags))}
            return (list(raw.keys()), raw, 0, None, None)

        def deserialize_transaction(self, tx_hex):
            return _StubInfo(self._flags[int(tx_hex.replace("hex", ""))])

    def make_backend(flags):
        backend = MagicMock()
        backend._parser._parser = _StubRawParser(flags)
        backend.getblockhash.return_value = "hash"
        backend.rpc.return_value = "blockhex"
        return backend

    # No CP-bearing tx -> False (block can be skipped).
    monkeypatch.setattr(block_validation, "backend_instance", make_backend([False, False]))
    assert block_validation.block_has_counterparty_data(500) is False

    # At least one CP-bearing tx -> True.
    monkeypatch.setattr(block_validation, "backend_instance", make_backend([False, True, False]))
    assert block_validation.block_has_counterparty_data(500) is True


def test_predicate_fail_safe_on_error(monkeypatch):
    """Any error in the predicate path -> True (never skip on uncertainty)."""
    backend = MagicMock()
    backend._parser._parser.parse_block.side_effect = RuntimeError("bitcoind down")
    backend.getblockhash.return_value = "hash"
    backend.rpc.return_value = "blockhex"
    monkeypatch.setattr(block_validation, "backend_instance", backend)
    assert block_validation.block_has_counterparty_data(500) is True


def test_predicate_no_parser_returns_true(monkeypatch):
    """If the Rust parser is unavailable -> True (cannot soundly skip)."""
    backend = MagicMock()
    backend._parser = None
    monkeypatch.setattr(block_validation, "backend_instance", backend)
    assert block_validation.block_has_counterparty_data(500) is True


# ---------------------------------------------------------------------------
# Detection truth: txs_have_counterparty_data over real Rust parser + fixtures
# ---------------------------------------------------------------------------


def test_detection_truth_with_real_parser():
    """The aggregate predicate consumes #754's signal correctly: a CP-era stamp
    is detected, a native stamp is not, and any() over a mix is True."""
    parser = FastTransactionParser()
    cp_hex = _load_tx_hex(_CP_TXID)
    native_hex = _load_tx_hex(_NATIVE_TXID)

    assert block_validation.txs_have_counterparty_data(parser, [cp_hex]) is True
    assert block_validation.txs_have_counterparty_data(parser, [native_hex]) is False
    assert block_validation.txs_have_counterparty_data(parser, [native_hex, cp_hex]) is True
    # Empty / coinbase-only blocks -> no CP data.
    assert block_validation.txs_have_counterparty_data(parser, []) is False
