"""Tests for prefetch_source_prevouts cache pre-warming helper.

prefetch_source_prevouts warms backend_instance.raw_transactions_cache with a
single batched RPC so that the per-candidate vin[0] source lookup in get_tx_info
becomes a cache hit. It must be strictly output-neutral and non-fatal: it only
issues one batched getrawtransaction_batch over the deduped set of first-input
prev hashes, skips coinbase/null-hash inputs, and swallows any backend error.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import index_core.util as util
from index_core.transaction_utils import prefetch_source_prevouts


def _ctx(prev_hash):
    """Build a fake deserialized tx whose vin[0] spends prev_hash."""
    prevout = SimpleNamespace(hash=prev_hash, n=0)
    vin = SimpleNamespace(prevout=prevout)
    return SimpleNamespace(vin=[vin])


def _ctx_no_prevout():
    """Build a fake coinbase-style tx whose vin[0] has no prevout."""
    return SimpleNamespace(vin=[SimpleNamespace(prevout=None)])


def test_prefetch_batches_deduped_vin0_hashes(monkeypatch):
    h1 = b"\x11" * 32
    h2 = b"\x22" * 32

    # tx_c reuses h1 to exercise dedupe; insertion order must be preserved.
    raw_transactions = {
        "tx_a": "hexA",
        "tx_b": "hexB",
        "tx_c": "hexC",
    }
    ctx_by_hex = {"hexA": _ctx(h1), "hexB": _ctx(h2), "hexC": _ctx(h1)}

    mock_backend = MagicMock()
    mock_backend.deserialize.side_effect = lambda tx_hex: ctx_by_hex[tx_hex]

    with patch("index_core.transaction_utils.backend_instance", mock_backend):
        prefetch_source_prevouts(raw_transactions)

    assert mock_backend.getrawtransaction_batch.call_count == 1
    args, kwargs = mock_backend.getrawtransaction_batch.call_args
    assert args[0] == [util.ib2h(h1), util.ib2h(h2)]
    assert kwargs.get("skip_missing") is True


def test_prefetch_excludes_coinbase_and_null_hash(monkeypatch):
    h1 = b"\x33" * 32
    null_hash = b"\x00" * 32

    raw_transactions = {
        "coinbase_null": "hexNull",
        "coinbase_noprevout": "hexNoPrevout",
        "real": "hexReal",
    }
    ctx_by_hex = {
        "hexNull": _ctx(null_hash),
        "hexNoPrevout": _ctx_no_prevout(),
        "hexReal": _ctx(h1),
    }

    mock_backend = MagicMock()
    mock_backend.deserialize.side_effect = lambda tx_hex: ctx_by_hex[tx_hex]

    with patch("index_core.transaction_utils.backend_instance", mock_backend):
        prefetch_source_prevouts(raw_transactions)

    assert mock_backend.getrawtransaction_batch.call_count == 1
    args, _ = mock_backend.getrawtransaction_batch.call_args
    assert args[0] == [util.ib2h(h1)]


def test_prefetch_no_candidates_skips_batch(monkeypatch):
    raw_transactions = {"coinbase": "hexCb"}
    mock_backend = MagicMock()
    mock_backend.deserialize.side_effect = lambda tx_hex: _ctx_no_prevout()

    with patch("index_core.transaction_utils.backend_instance", mock_backend):
        prefetch_source_prevouts(raw_transactions)

    mock_backend.getrawtransaction_batch.assert_not_called()


def test_prefetch_swallows_backend_exception(monkeypatch):
    raw_transactions = {"tx_a": "hexA"}
    mock_backend = MagicMock()
    mock_backend.deserialize.side_effect = RuntimeError("boom")

    with patch("index_core.transaction_utils.backend_instance", mock_backend):
        # Must not raise; failure leaves the existing serial fetch as fallback.
        prefetch_source_prevouts(raw_transactions)

    mock_backend.getrawtransaction_batch.assert_not_called()
