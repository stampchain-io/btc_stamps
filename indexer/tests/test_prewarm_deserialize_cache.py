"""Tests for OPP-3 (#793) — Backend.deserialize cache pre-warming via the
Rust parser's parallel ``batch_parse_transactions`` during ``get_tx_list``.

Key invariants:
- Pre-warmed entries match what ``deserialize`` would have produced per-tx
  (cache key = tx_hex, cache value = TransactionInfo).
- Non-included txs are NOT cached (Rust filters those out) — subsequent
  ``deserialize`` calls fall through to the per-tx lazy path (status quo).
- Any failure in ``_prewarm_deserialize_cache`` is swallowed and indexing
  continues with the existing per-tx fallback — this method is pure
  performance, must never break correctness.
- ``config.PREWARM_DESERIALIZE_CACHE`` gates the call (default true).
"""

import os
from unittest.mock import MagicMock, patch

os.environ["TESTING"] = "1"
os.environ["USE_TEST_DB"] = "1"
os.environ["MOCK_DB"] = "1"
os.environ["RPC_USER"] = "rpc"
os.environ["RPC_PASSWORD"] = "rpc"
os.environ["RPC_IP"] = "127.0.0.1"
os.environ["RPC_PORT"] = "8332"


def _make_backend_with_parser(parser_result):
    """Build a Backend instance with a mocked Rust parser whose
    ``batch_parse_transactions`` returns ``parser_result``."""
    from index_core.backend import Backend

    backend = Backend()
    parser = MagicMock()
    parser.batch_parse_transactions = MagicMock(return_value=parser_result)
    backend._parser = parser
    # Replace the cache with a real instance so .set/.get behaves like prod.
    cache = MagicMock()
    cache.set = MagicMock()
    cache.get = MagicMock(return_value=None)
    backend.deserialized_tx_cache = cache
    return backend, parser, cache


def _tx_info(txid):
    info = MagicMock()
    info.txid = txid
    return info


def test_prewarm_caches_included_subset():
    """The Rust batch returns the should_include subset; cache must be
    keyed by tx_hex (not txid) so per-tx ``deserialize(tx_hex)`` hits."""
    info_a = _tx_info("txid_A")
    info_c = _tx_info("txid_C")
    # Block has 3 txs; only A and C are stamp candidates per Rust filter.
    raw_transactions = {"txid_A": "hex_A", "txid_B": "hex_B", "txid_C": "hex_C"}

    backend, parser, cache = _make_backend_with_parser([info_a, info_c])
    backend._prewarm_deserialize_cache(raw_transactions)

    parser.batch_parse_transactions.assert_called_once()
    # Cache set called twice (A and C), NOT three times.
    assert cache.set.call_count == 2
    cache.set.assert_any_call("hex_A", info_a)
    cache.set.assert_any_call("hex_C", info_c)
    # B was filtered out by Rust — must NOT be cached.
    cached_hexes = {call.args[0] for call in cache.set.call_args_list}
    assert "hex_B" not in cached_hexes


def test_prewarm_no_op_when_empty():
    """Empty raw_transactions dict → no parser call, no cache set."""
    backend, parser, cache = _make_backend_with_parser([])
    backend._prewarm_deserialize_cache({})
    assert not parser.batch_parse_transactions.called
    assert not cache.set.called


def test_prewarm_no_op_when_parser_unavailable():
    """If the Rust parser isn't loaded, the pre-warm is a silent no-op."""
    from index_core.backend import Backend

    backend = Backend()
    backend._parser = None
    cache = MagicMock()
    cache.set = MagicMock()
    backend.deserialized_tx_cache = cache

    backend._prewarm_deserialize_cache({"txid_A": "hex_A"})
    assert not cache.set.called


def test_prewarm_swallows_parser_exception():
    """Any failure during pre-warm must NOT raise — correctness is preserved
    by the existing per-tx lazy ``deserialize`` fallback."""
    from index_core.backend import Backend

    backend = Backend()
    parser = MagicMock()
    parser.batch_parse_transactions = MagicMock(side_effect=RuntimeError("boom"))
    backend._parser = parser
    cache = MagicMock()
    cache.set = MagicMock()
    backend.deserialized_tx_cache = cache

    # Must not raise.
    backend._prewarm_deserialize_cache({"txid_A": "hex_A"})
    assert not cache.set.called


def test_prewarm_handles_unknown_txid_in_result():
    """If the parser returns a TransactionInfo with an unexpected txid
    (shouldn't happen, but defensively): skip it, don't crash and don't
    blindly cache against a wrong tx_hex."""
    info_x = _tx_info("not_in_block")
    raw_transactions = {"txid_A": "hex_A"}

    backend, parser, cache = _make_backend_with_parser([info_x])
    backend._prewarm_deserialize_cache(raw_transactions)

    # No cache set for the mystery txid; no crash.
    assert not cache.set.called


def test_get_tx_list_invokes_prewarm_by_default():
    """The pre-warm hook is wired into get_tx_list and runs by default."""
    from index_core.backend import Backend

    backend = Backend()
    parser = MagicMock()
    raw = {"a": "hex_a"}
    parser.parse_block = MagicMock(return_value=(["a"], raw, 1700000000, "prev_hash", None))
    parser.batch_parse_transactions = MagicMock(return_value=[])
    backend._parser = parser
    backend.deserialized_tx_cache = MagicMock()
    backend.rpc = MagicMock(return_value="raw_block_hex")

    # Default config (PREWARM_DESERIALIZE_CACHE=true).
    with patch("index_core.backend.config", new=MagicMock(PREWARM_DESERIALIZE_CACHE=True)):
        backend.get_tx_list("blockhash")

    parser.batch_parse_transactions.assert_called_once()


def test_get_tx_list_skips_prewarm_when_disabled():
    """Operator can turn off the pre-warm via PREWARM_DESERIALIZE_CACHE=false."""
    from index_core.backend import Backend

    backend = Backend()
    parser = MagicMock()
    raw = {"a": "hex_a"}
    parser.parse_block = MagicMock(return_value=(["a"], raw, 1700000000, "prev_hash", None))
    parser.batch_parse_transactions = MagicMock(return_value=[])
    backend._parser = parser
    backend.deserialized_tx_cache = MagicMock()
    backend.rpc = MagicMock(return_value="raw_block_hex")

    with patch("index_core.backend.config", new=MagicMock(PREWARM_DESERIALIZE_CACHE=False)):
        backend.get_tx_list("blockhash")

    assert not parser.batch_parse_transactions.called
