"""
The direct-fetch path must not read Counterparty data for a block CP has not parsed.

An unparsed block reads as a block with no Counterparty transactions, so its stamps
were skipped. This happened on ECX at block 974676: the indexer fetched the block 13
blocks behind the node tip, CP parsed it 20 seconds later, and the OLGA stamp in it
was never indexed. The old guard only waited for CP within 2 blocks of the node tip.
"""

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

from index_core import fetch_utils

NODE = {"name": "test-node", "url": "http://test:4000/v2"}


@pytest.fixture(autouse=True)
def reset_cp_height():
    fetch_utils._cp_parsed_height = 0
    yield
    fetch_utils._cp_parsed_height = 0


def _status(height, caught_up=True):
    return ("11.5.0", {"last_block": height, "db_caught_up": caught_up})


def test_ensure_waits_until_cp_has_parsed_the_block():
    responses = [_status(974675), _status(974675), _status(974676)]
    with patch("index_core.fetch_utils.get_healthy_nodes", return_value=[NODE]), patch(
        "index_core.fetch_utils.fetch_node_version_v2", side_effect=responses
    ) as status, patch("index_core.fetch_utils.time.sleep"):
        assert fetch_utils.ensure_cp_processed(974676, max_wait=30.0) is True
    assert status.call_count == 3
    assert fetch_utils.cp_parsed_height() == 974676


def test_ensure_returns_false_when_cp_never_reaches_the_block():
    clock = iter(range(0, 1000, 10))
    with patch("index_core.fetch_utils.get_healthy_nodes", return_value=[NODE]), patch(
        "index_core.fetch_utils.fetch_node_version_v2", return_value=_status(974675)
    ), patch("index_core.fetch_utils.time.sleep"), patch(
        "index_core.fetch_utils.time.time", side_effect=lambda: next(clock)
    ):
        assert fetch_utils.ensure_cp_processed(974676, max_wait=30.0) is False
    assert fetch_utils.cp_parsed_height() == 974675


def test_ensure_makes_no_call_for_blocks_cp_is_already_past():
    with patch("index_core.fetch_utils.get_healthy_nodes", return_value=[NODE]), patch(
        "index_core.fetch_utils.fetch_node_version_v2", return_value=_status(977000)
    ) as status:
        assert fetch_utils.ensure_cp_processed(976000) is True
        assert status.call_count == 1
        for block in range(976001, 977001):
            assert fetch_utils.ensure_cp_processed(block) is True
        assert status.call_count == 1  # bulk catch-up costs one status call


def test_height_not_recorded_while_cp_is_not_caught_up():
    clock = iter(range(0, 1000, 10))
    with patch("index_core.fetch_utils.get_healthy_nodes", return_value=[NODE]), patch(
        "index_core.fetch_utils.fetch_node_version_v2", return_value=_status(977000, caught_up=False)
    ), patch("index_core.fetch_utils.time.sleep"), patch(
        "index_core.fetch_utils.time.time", side_effect=lambda: next(clock)
    ):
        assert fetch_utils.ensure_cp_processed(976000, max_wait=30.0) is False
    assert fetch_utils.cp_parsed_height() == 0


def _direct_fetch_branch():
    """The else-branch of `if blocks_from_tip <= 2` in follow(): the far-from-tip direct fetch."""
    src = Path(__file__).resolve().parents[1] / "src" / "index_core" / "blocks.py"
    tree = ast.parse(src.read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "blocks_from_tip"
        ):
            return node
    raise AssertionError("blocks_from_tip branch not found in blocks.py")


def _calls(nodes):
    names = []
    for n in nodes:
        for sub in ast.walk(n):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                names.append(sub.func.id)
    return names


def test_far_from_tip_branch_waits_for_cp_before_fetching():
    branch = _direct_fetch_branch()
    # Prove the extractor finds the real branch: the near-tip side has the old wait.
    assert "wait_for_cp_block_processed" in _calls(branch.body)
    assert "ensure_cp_processed" in _calls(branch.orelse)
