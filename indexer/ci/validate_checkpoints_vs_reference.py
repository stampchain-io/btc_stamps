#!/usr/bin/env python3
"""Cross-check CHECKPOINTS_MAINNET against snapshots/reference_hashes.json.

CHECKPOINTS_MAINNET in indexer/src/index_core/check.py is the runtime
self-check baseline — the indexer halts on mismatch as it processes blocks.
reference_hashes.json is the canonical replay baseline (every block) used by
reparse and the new ci_consensus_hashes.json. The two are independently
maintained; if a maintainer edits CHECKPOINTS_MAINNET without refreshing
reference_hashes.json (or vice versa), silent divergence is a real risk and
exactly the kind of file-sync footgun this script catches at PR time.

This is the script-form of the cross-check in indexer/tools/validate_hashes.py
adapted for CI — it AST-parses CHECKPOINTS_MAINNET out of check.py rather
than importing the module (avoids pulling in config, fetch_utils,
node_health, etc., which would need the full poetry venv), and it exits
non-zero on mismatch so CI fails closed.

Exit codes:
  0 — every CHECKPOINTS_MAINNET entry matches reference_hashes.json
  1 — any divergence (or missing block from reference_hashes.json)
  2 — invocation error (file not found, parse failure)
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


def parse_config_constants(config_py_path: Path) -> dict[str, int]:
    """Extract integer module-level constants from config.py via AST.

    CHECKPOINTS_MAINNET keys reference `config.CP_STAMP_GENESIS_BLOCK` etc.
    rather than literal block numbers, so we need their resolved values to
    evaluate the dict.
    """
    constants: dict[str, int] = {}
    tree = ast.parse(config_py_path.read_text())
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        if value is None:
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, int):
            for tgt in targets:
                if isinstance(tgt, ast.Name):
                    constants[tgt.id] = value.value
    return constants


def evaluate_node(node: ast.AST, config_constants: dict[str, int]) -> Any:
    """Recursively evaluate an AST node, resolving `config.NAME` references."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == "config":
            if node.attr in config_constants:
                return config_constants[node.attr]
            raise RuntimeError(f"config.{node.attr} not found in config.py")
        raise RuntimeError(f"unsupported attribute: {ast.dump(node)}")
    if isinstance(node, ast.Dict):
        return {evaluate_node(k, config_constants): evaluate_node(v, config_constants) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.List):
        return [evaluate_node(e, config_constants) for e in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(evaluate_node(e, config_constants) for e in node.elts)
    raise RuntimeError(f"unsupported node type: {type(node).__name__}")


def parse_checkpoints(check_py_path: Path, config_py_path: Path) -> dict[int, dict[str, str]]:
    """Extract CHECKPOINTS_MAINNET from check.py without executing it.

    Avoids importing check.py (which would pull in config, fetch_utils,
    node_health, etc.). Returns {block_index: {ledger_hash, txlist_hash}}.
    """
    config_constants = parse_config_constants(config_py_path)
    tree = ast.parse(check_py_path.read_text())
    for node in tree.body:
        target_name: str | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value = node.value
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "CHECKPOINTS_MAINNET":
                    target_name = tgt.id
                    value = node.value
                    break
        if target_name == "CHECKPOINTS_MAINNET" and value is not None:
            return evaluate_node(value, config_constants)
    raise RuntimeError(f"CHECKPOINTS_MAINNET not found in {check_py_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--check-py",
        default="indexer/src/index_core/check.py",
        help="path to check.py (relative to repo root)",
    )
    ap.add_argument(
        "--config-py",
        default="indexer/src/config.py",
        help="path to config.py (relative to repo root)",
    )
    ap.add_argument(
        "--reference",
        default="indexer/snapshots/reference_hashes.json",
        help="path to reference_hashes.json (relative to repo root)",
    )
    args = ap.parse_args()

    check_py = Path(args.check_py)
    config_py = Path(args.config_py)
    reference_path = Path(args.reference)

    for p, label in [(check_py, "check.py"), (config_py, "config.py"), (reference_path, "reference_hashes.json")]:
        if not p.exists():
            print(f"::error::{label} not found at {p}", file=sys.stderr)
            return 2

    try:
        checkpoints = parse_checkpoints(check_py, config_py)
    except Exception as e:
        print(f"::error::failed to parse CHECKPOINTS_MAINNET from {check_py}: {e}", file=sys.stderr)
        return 2

    with open(reference_path) as f:
        reference = json.load(f).get("hashes", {})

    print(f"Validating {len(checkpoints)} CHECKPOINTS_MAINNET entries against {reference_path}\n")

    missing: list[int] = []
    mismatched: list[tuple[int, str, str, str]] = []  # (block, field, expected, actual)

    for block_index, expected in checkpoints.items():
        ref = reference.get(str(block_index))
        if ref is None:
            missing.append(block_index)
            continue
        # txlist_hash always required
        if expected.get("txlist_hash") and expected["txlist_hash"] != ref.get("txlist_hash"):
            mismatched.append((block_index, "txlist_hash", expected["txlist_hash"], ref.get("txlist_hash", "<missing>")))
        # ledger_hash only checked when CHECKPOINTS_MAINNET carries a value
        if expected.get("ledger_hash") and expected["ledger_hash"] != ref.get("ledger_hash"):
            mismatched.append((block_index, "ledger_hash", expected["ledger_hash"], ref.get("ledger_hash", "<missing>")))

    if missing:
        print(f"::error::{len(missing)} CHECKPOINTS_MAINNET blocks missing from reference_hashes.json")
        for b in sorted(missing)[:20]:
            print(f"  block {b}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")

    if mismatched:
        print(f"::error::{len(mismatched)} hash mismatches between CHECKPOINTS_MAINNET and reference_hashes.json")
        for block, field, expected, actual in mismatched[:20]:
            print(f"  block {block} {field}:")
            print(f"    CHECKPOINTS_MAINNET: {expected}")
            print(f"    reference_hashes:    {actual}")
        if len(mismatched) > 20:
            print(f"  ... and {len(mismatched) - 20} more")

    if missing or mismatched:
        print(
            "\nFix: either update CHECKPOINTS_MAINNET in check.py to match the "
            "reference baseline, or refresh reference_hashes.json (and any derived "
            "files like ci_consensus_hashes.json) from a validated source.",
            file=sys.stderr,
        )
        return 1

    print(f"All {len(checkpoints)} CHECKPOINTS_MAINNET entries match reference_hashes.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
