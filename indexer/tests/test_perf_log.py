"""Unit tests for the flag-gated per-block perf logger (index_core.perf_log).

Pure-unit: no DB, no network. Verifies that ``record_block_perf`` writes a
valid JSONL line with the expected keys and that any backend/IO error is
swallowed (the helper must never raise, so perf logging can't disrupt block
processing).
"""

import json

from index_core.perf_log import record_block_perf

EXPECTED_KEYS = {
    "block_index",
    "n_txs",
    "n_candidates",
    "t_fetch_ms",
    "t_filter_ms",
    "t_decode_ms",
    "t_hash_ms",
    "t_dbwrite_ms",
    "t_total_ms",
    "version",
}


def _sample_fields():
    return {
        "block_index": 840000,
        "n_txs": 3000,
        "n_candidates": 12,
        "t_fetch_ms": 10.5,
        "t_filter_ms": 1.25,
        "t_decode_ms": 42.0,
        "t_hash_ms": 3.0,
        "t_dbwrite_ms": 7.5,
        "t_total_ms": 64.25,
        "version": "1.8.26+canary.322",
    }


def test_record_block_perf_writes_valid_jsonl_line(tmp_path):
    """A single call appends one parseable JSON object with the expected keys."""
    path = tmp_path / "perf_log.jsonl"
    fields = _sample_fields()

    record_block_perf(str(path), fields)

    contents = path.read_text(encoding="utf-8")
    lines = contents.splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert set(parsed.keys()) == EXPECTED_KEYS
    assert parsed == fields


def test_record_block_perf_appends_one_line_per_call(tmp_path):
    """Repeated calls append; they do not truncate the file."""
    path = tmp_path / "perf_log.jsonl"

    record_block_perf(str(path), _sample_fields())
    record_block_perf(str(path), _sample_fields())

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        assert set(json.loads(line).keys()) == EXPECTED_KEYS


def test_record_block_perf_swallows_io_error(tmp_path):
    """A backend/IO error (path is a directory) is swallowed -- no raise."""
    # Opening a directory for append raises IsADirectoryError; the helper must
    # log-and-swallow rather than propagate.
    record_block_perf(str(tmp_path), _sample_fields())


def test_record_block_perf_swallows_serialization_error(tmp_path):
    """A non-JSON-serializable payload is swallowed -- no raise, no partial write."""
    path = tmp_path / "perf_log.jsonl"

    record_block_perf(str(path), {"block_index": object()})

    assert not path.exists()
