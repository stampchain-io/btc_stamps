"""Unit tests for indexer/ci/ci_reparse_multi.py helpers.

Covers only the pure-Python schema-handling utilities — `stitch_prev_anchor`
in particular. Full end-to-end runs of the runner against the curated
boundary set need network access (bitcoind + counterparty.io public API)
and run as part of the reparse-consensus validation workflow, not here.
"""

from __future__ import annotations

import importlib.util
import os
import sys


def _load_runner_module():
    """Importable handle to ci/ci_reparse_multi.py without running main()."""
    here = os.path.dirname(os.path.abspath(__file__))
    runner_path = os.path.normpath(os.path.join(here, "..", "ci", "ci_reparse_multi.py"))
    spec = importlib.util.spec_from_file_location("ci_reparse_multi", runner_path)
    assert spec and spec.loader, f"could not load {runner_path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ci_reparse_multi"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_stitch_prev_anchor_injects_synthetic_prior_block():
    runner = _load_runner_module()
    ref = {}
    entry = {
        "block_hash": "block-N",
        "prev_block_hash": "block-N-1",
        "prev_ledger_hash": "ledger-N-1",
        "prev_txlist_hash": "txlist-N-1",
        "prev_messages_hash": "messages-N-1",
    }
    stitched = runner.stitch_prev_anchor(ref, 900_000, entry)
    assert stitched is True
    assert ref["899999"] == {
        "block_hash": "block-N-1",
        "ledger_hash": "ledger-N-1",
        "txlist_hash": "txlist-N-1",
        "messages_hash": "messages-N-1",
    }


def test_stitch_prev_anchor_no_op_when_prior_already_present():
    runner = _load_runner_module()
    existing_prior = {
        "block_hash": "from-reference",
        "ledger_hash": "from-reference",
        "txlist_hash": "from-reference",
        "messages_hash": "from-reference",
    }
    ref = {"899999": existing_prior}
    entry = {"block_hash": "block-N", "prev_block_hash": "would-overwrite"}
    stitched = runner.stitch_prev_anchor(ref, 900_000, entry)
    assert stitched is False
    assert ref["899999"] is existing_prior, "must not overwrite an existing reference_hashes.json entry"


def test_stitch_prev_anchor_skips_entries_without_prev_block_hash():
    """Genesis-block curated entry has no prev_block_hash; runner must not
    inject a degenerate all-empty anchor that would mask a real bug."""
    runner = _load_runner_module()
    ref = {}
    entry = {"block_hash": "block-genesis"}
    stitched = runner.stitch_prev_anchor(ref, 779_652, entry)
    assert stitched is False
    assert "779651" not in ref
