#!/usr/bin/env python3
"""Guard: consensus-critical packages must be exact-pinned AND installed at the pin.

Issue #759. A version flip in any of these packages can silently change indexer
output and break consensus with the production RDS:

  * regex      — used in MIME-detection regexes
  * PyNaCl     — signature / key handling
  * pybase64   — SIMD base64 decoder; validate=True behavior varies across versions

This script enforces two invariants in CI, on every Python version in the
reparse-validate matrix (so it also proves the SAME versions install on
3.10 / 3.11 / 3.12):

  1. Each package is declared with an EXACT version in pyproject.toml
     (a bare ``name = "x.y.z"`` — no caret/tilde/range/wildcard), so
     ``poetry update`` cannot move it.
  2. The version actually installed in the environment equals that pin.

``btc_stamps_parser`` (the Rust wheel) is built per-environment rather than
pinned as a PyPI version, so it is reported but not pin-checked here; the
freeze-drift workflow + build pipeline cover it.

Exit 0 if all invariants hold, 1 otherwise. No network, no indexer import.
"""

from __future__ import annotations

import importlib.metadata as md
import os
import re
import sys

# Distribution name -> import/metadata name. pyproject keys are lower-case.
CONSENSUS_PACKAGES = ["regex", "pynacl", "pybase64"]

HERE = os.path.dirname(os.path.abspath(__file__))
PYPROJECT = os.path.normpath(os.path.join(HERE, "..", "pyproject.toml"))

# Matches a bare exact pin in [tool.poetry.dependencies], e.g. `regex = "2026.2.28"`.
# Deliberately rejects caret/tilde/range/wildcard/markers so a loosened
# constraint fails the guard instead of silently allowing drift.
_EXACT = re.compile(r'^\s*(?P<name>[A-Za-z0-9_.-]+)\s*=\s*"(?P<ver>[0-9][^"^~><=*,\s]*)"\s*$')


def _declared_pins(path: str) -> dict[str, str]:
    """Return {lower_name: exact_version} for bare-string deps in pyproject."""
    pins: dict[str, str] = {}
    for line in open(path, encoding="utf-8"):
        m = _EXACT.match(line)
        if m:
            pins[m.group("name").lower()] = m.group("ver")
    return pins


def main() -> int:
    pins = _declared_pins(PYPROJECT)
    failures: list[str] = []

    print(f"Consensus package pin guard (Python {sys.version.split()[0]})")
    print(f"  pyproject: {PYPROJECT}\n")

    for pkg in CONSENSUS_PACKAGES:
        declared = pins.get(pkg)
        try:
            installed = md.version(pkg)
        except md.PackageNotFoundError:
            installed = None

        if declared is None:
            failures.append(f'{pkg}: not exact-pinned in pyproject.toml (must be a bare `"x.y.z"`)')
            print(f"  ✗ {pkg}: no exact pin found in pyproject")
            continue
        if installed is None:
            failures.append(f"{pkg}: pinned {declared} but not installed")
            print(f"  ✗ {pkg}: pinned {declared}, not installed")
            continue
        if installed != declared:
            failures.append(f"{pkg}: installed {installed} != pinned {declared}")
            print(f"  ✗ {pkg}: installed {installed} != pinned {declared}")
            continue
        print(f"  ✓ {pkg}: {installed} (exact-pinned)")

    # Informational: the Rust wheel is built per-env, not PyPI-pinned.
    try:
        print(f"\n  (info) btc-stamps-parser: {md.version('btc-stamps-parser')} — built per-env, not pin-checked")
    except md.PackageNotFoundError:
        pass

    if failures:
        print("\nCONSENSUS PIN DRIFT DETECTED:")
        for f in failures:
            print(f"  - {f}")
        print(
            "\nFix: pin the package to an exact version in indexer/pyproject.toml and "
            "`poetry lock` so the installed version matches. See #759."
        )
        return 1

    print("\nAll consensus-critical packages are exact-pinned and match. ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
