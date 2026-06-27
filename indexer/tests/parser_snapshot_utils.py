"""Helpers for the Rust-parser snapshot test (issue #765).

The Rust parser ``btc_stamps_parser.FastTransactionParser`` turns raw
transaction bytes into a ``TransactionInfo`` whose fields
(``has_valid_pattern`` / ``has_valid_data`` / ``keyburn`` / ``should_include``
plus the per-output multisig/keyburn classification) are the consensus-relevant
output of the parser. That output is a *pure function of the transaction bytes*
— no DB, no network, no Bitcoin node — yet a bump to a consensus-surface crate
(``bitcoin``, ``pyo3``, ``hex``, ``rand``) could silently move it.

This module captures that output for a committed corpus of real stamp
transactions so a unit test can assert byte-exact stability on every PR,
catching parser drift in seconds instead of via a 24-48h from-genesis reindex.
See ``tests/test_parser_snapshots.py`` and
``tests/fixtures/parser_snapshots/README.md``.

Regenerate the snapshot with ``tests/fixtures/parser_snapshots/refresh.sh``
(a thin wrapper around ``python -m tests.parser_snapshot_utils``).
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List

from tests.bitcoin_fixtures_loader import BitcoinFixturesLoader

# tests/ — resolve fixture paths relative to this file so callers' cwd is irrelevant.
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_TRANSACTION_CACHE_DIR = os.path.join(_TESTS_DIR, "fixtures", "transaction_cache")
SNAPSHOT_PATH = os.path.join(_TESTS_DIR, "fixtures", "parser_snapshots", "parser_snapshots.json")

ISSUE_URL = "https://github.com/stampchain-io/btc_stamps/issues/765"
REFRESH_HINT = "tests/fixtures/parser_snapshots/refresh.sh"


def serialize_transaction_info(info: Any) -> Dict[str, Any]:
    """Serialize a ``TransactionInfo`` into a plain, JSON-stable dict.

    Captures every field the Rust parser exposes, so any drift in parser output
    — value changes *or* a field appearing/disappearing — surfaces as a diff.
    Key order here is irrelevant: the snapshot file is written ``sort_keys=True``.
    """
    return {
        "version": info.version,
        "txid": info.txid,
        "has_valid_pattern": info.has_valid_pattern,
        "has_valid_data": info.has_valid_data,
        "keyburn": info.keyburn,
        "should_include": info.should_include,
        "inputs": [
            {
                "prev_txid": inp.prev_txid,
                "prev_vout": inp.prev_vout,
                "sequence": inp.sequence,
            }
            for inp in info.inputs
        ],
        "outputs": [
            {
                "index": out.index,
                "value": out.value,
                "script_hex": out.script_hex,
                "script_pubkey": out.script_pubkey,
                "has_op_checkmultisig": out.has_op_checkmultisig,
                "keyburn": out.keyburn,
                "last_pubkey": out.last_pubkey,
                "third_pubkey": out.third_pubkey,
            }
            for out in info.outputs
        ],
    }


def collect_corpus() -> List[Dict[str, Any]]:
    """Collect the fixture transaction corpus (raw hex + provenance), DB/network-free.

    Both sources are committed to git:

    * ``tests/fixtures/transaction_cache/*.json`` — real stamp transactions, each
      carrying a ``hex`` field and ``block_height``.
    * ``tests/fixtures/bitcoin_node_fixtures.json`` — the ``special_transactions``
      list used by the migrated Bitcoin-node tests.

    Returns the corpus sorted by txid so the generated snapshot is deterministic.
    """
    corpus: List[Dict[str, Any]] = []

    for path in glob.glob(os.path.join(_TRANSACTION_CACHE_DIR, "*.json")):
        with open(path) as fh:
            data = json.load(fh)
        tx_hex = data.get("hex")
        if not tx_hex:
            # Not a transaction fixture (e.g. fetch_summary.json).
            continue
        corpus.append(
            {
                "txid": data["tx_hash"],
                "source": "transaction_cache",
                "block_height": data.get("block_height"),
                "tx_hex": tx_hex,
            }
        )

    loader = BitcoinFixturesLoader()
    for tx in loader.get_special_transactions():
        corpus.append(
            {
                "txid": tx["txid"],
                "source": "bitcoin_node_fixtures.special_transactions",
                "block_height": None,
                "tx_hex": tx["hex"],
            }
        )

    corpus.sort(key=lambda entry: entry["txid"])
    return corpus


def build_snapshot() -> Dict[str, Any]:
    """Run the live Rust parser over the corpus and return the snapshot dict."""
    # Imported lazily so merely importing this module never hard-requires the
    # compiled Rust extension to be built.
    from btc_stamps_parser import FastTransactionParser

    parser = FastTransactionParser()
    snapshots: List[Dict[str, Any]] = []
    for entry in collect_corpus():
        info = parser.deserialize_transaction(entry["tx_hex"])
        # Guard the corpus itself: the parser derives the txid from the bytes,
        # so a mismatch means the fixture's hex and tx_hash disagree.
        if info.txid != entry["txid"]:
            raise AssertionError(
                f"Corpus txid mismatch ({entry['source']}): fixture claims "
                f"{entry['txid']} but the parser derived {info.txid} from its hex."
            )
        snapshots.append(
            {
                "txid": entry["txid"],
                "source": entry["source"],
                "block_height": entry["block_height"],
                "tx_hex": entry["tx_hex"],
                "expected": serialize_transaction_info(info),
            }
        )

    return {
        "_comment": (
            "Byte-exact output snapshots of the Rust parser "
            "(btc_stamps_parser.FastTransactionParser) over a committed corpus of "
            "real stamp transactions. Regenerate ONLY after an intentional, "
            "reindex-validated parser/consensus change, via "
            f"{REFRESH_HINT}. See issue #765."
        ),
        "_issue": ISSUE_URL,
        "_refresh": REFRESH_HINT,
        "parser_module": "btc_stamps_parser",
        "snapshots": snapshots,
    }


def load_snapshot() -> Dict[str, Any]:
    """Load the committed snapshot file."""
    with open(SNAPSHOT_PATH) as fh:
        return json.load(fh)


def write_snapshot(snapshot: Dict[str, Any]) -> None:
    """Write the snapshot deterministically (sorted keys, trailing newline)."""
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    with open(SNAPSHOT_PATH, "w") as fh:
        json.dump(snapshot, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main() -> int:
    snapshot = build_snapshot()
    write_snapshot(snapshot)
    entries = snapshot["snapshots"]
    total = len(entries)
    includes = sum(1 for s in entries if s["expected"]["should_include"])
    patterns = sum(1 for s in entries if s["expected"]["has_valid_pattern"])
    print(f"Wrote {total} parser snapshots -> {SNAPSHOT_PATH}")
    print(f"  should_include=True: {includes}/{total}   has_valid_pattern (P2WSH/OLGA): {patterns}/{total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
