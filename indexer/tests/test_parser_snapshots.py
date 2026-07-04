"""Snapshot test for the Rust transaction parser (issue #765).

Asserts the parser's byte-exact output against a committed snapshot for a
corpus of real stamp transactions. Runs at unit-test speed with no DB, no
docker, and no network — it only needs the built ``btc_stamps_parser``
extension. It catches consensus drift in parser output (e.g. from a
``bitcoin`` / ``pyo3`` / ``hex`` / ``rand`` crate bump) without a from-genesis
reindex.

If this test fails after an INTENTIONAL parser change that has been validated
against prod via a full reindex, refresh the baseline in the same PR:

    ./tests/fixtures/parser_snapshots/refresh.sh
"""

import pytest

from tests.parser_snapshot_utils import (
    REFRESH_HINT,
    build_snapshot,
    collect_corpus,
    load_snapshot,
    serialize_transaction_info,
)

# The parser is a compiled Rust extension. If it isn't built, skip the module
# cleanly (mirrors how the other rust-parser tests degrade) rather than erroring
# at collection time.
FastTransactionParser = pytest.importorskip("btc_stamps_parser").FastTransactionParser

_SNAPSHOT = load_snapshot()
_ENTRIES = _SNAPSHOT["snapshots"]


def _case_id(entry):
    kind = "cache" if entry["source"] == "transaction_cache" else "special"
    return f"{kind}-{entry['txid'][:12]}"


def test_snapshot_is_non_empty():
    """A truncated/empty snapshot must not silently pass the parametrized test."""
    assert _ENTRIES, f"parser_snapshots.json has no entries; run {REFRESH_HINT}"


@pytest.mark.parametrize("entry", _ENTRIES, ids=[_case_id(e) for e in _ENTRIES])
def test_parser_output_matches_snapshot(entry):
    """The live parser reproduces the committed output for each fixture, byte-for-byte."""
    parser = FastTransactionParser()
    info = parser.deserialize_transaction(entry["tx_hex"])
    actual = serialize_transaction_info(info)
    assert actual == entry["expected"], (
        f"Rust parser output drifted for tx {entry['txid']} (source={entry['source']}). "
        f"If this change is intentional and reindex-validated, refresh {REFRESH_HINT}."
    )


def test_snapshot_is_in_sync_with_fixture_corpus():
    """Adding/removing a fixture without refreshing the snapshot fails loudly."""
    corpus_txids = {e["txid"] for e in collect_corpus()}
    snapshot_txids = {e["txid"] for e in _ENTRIES}
    missing = corpus_txids - snapshot_txids
    stale = snapshot_txids - corpus_txids
    assert not missing and not stale, (
        f"parser_snapshots.json is out of sync with the fixture corpus "
        f"(missing={sorted(missing)}, stale={sorted(stale)}). Run {REFRESH_HINT}."
    )


def test_corpus_covers_parser_code_paths():
    """The corpus exercises each Rust-parser classification branch.

    At the Rust layer the consensus-relevant branches are: P2WSH/OLGA pattern
    detection, multisig keyburn detection, the ARC4 PREFIX check (valid-data
    both True and False), and the resulting should_include (both True and
    False). MIME type and SRC-20/721/101 class are decided downstream in Python
    and are invisible at this layer, so they are not asserted here.
    """
    expected = [e["expected"] for e in _ENTRIES]
    assert any(e["has_valid_pattern"] for e in expected), "corpus has no P2WSH/OLGA fixture"
    assert any(e["keyburn"] for e in expected), "corpus has no keyburn fixture"
    assert any(e["should_include"] for e in expected), "corpus has no included (valid stamp) fixture"
    assert any(not e["should_include"] for e in expected), "corpus has no excluded fixture (negative branch)"
    assert any(e["has_valid_data"] for e in expected), "corpus has no valid-data fixture"
    assert any(not e["has_valid_data"] for e in expected), "corpus has no invalid-data fixture"


def test_committed_snapshot_equals_fresh_build():
    """The committed file is exactly what the generator produces from the corpus.

    Strongest single guard: covers value drift, membership drift, and wrapper
    field/ordering drift in one shot. (Per-tx granularity for debugging which
    transactions moved lives in ``test_parser_output_matches_snapshot``.)
    """
    fresh = build_snapshot()
    assert fresh["snapshots"] == _ENTRIES, f"Committed snapshot differs from a fresh build; run {REFRESH_HINT}."
