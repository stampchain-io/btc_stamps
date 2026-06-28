# CI/CD Workflows

This document describes the GitHub Actions workflows for the BTC Stamps Indexer. It is
generated from the actual files in [`.github/workflows/`](../../.github/workflows/) — keep
it in sync when workflows change.

> **Python versions:** the project supports **3.10 / 3.11 / 3.12** (`pyproject.toml`:
> `python = "^3.10"`). The unit-test matrix runs all three; there is no Python 3.9.

## Workflow Index

| File | Name | Trigger(s) |
|------|------|-----------|
| `python-check.yml` | CI | `pull_request`, `workflow_dispatch` |
| `reparse-validate.yml` | Reparse Consensus Validation | `pull_request` (consensus paths), `workflow_dispatch` |
| `freeze-drift.yml` | Freeze Drift Check | `pull_request` (dep paths), `workflow_dispatch` |
| `coverage.yml` | Coverage Analysis | `pull_request` + `push` to `main`/`dev`, `workflow_dispatch` |
| `docker-auto-publish.yml` | Docker Auto-Publish | `push` to `main`/`dev` (indexer/docker paths) |
| `docker-publish.yml` | Docker Build and Publish | `workflow_dispatch` (tag + environment) |
| `version-check.yml` | Version Format Check | `push` + `pull_request` to `main`/`dev` |
| `bump-version.yml` | Bump Version | `push` to `dev`/`main`, `pull_request` closed, `workflow_dispatch` |
| `build-test.yml` | Build Tests | `workflow_call` (reusable) |
| `setup-python.yml` | Setup Python Environment | `workflow_call` (reusable) |
| `claude.yml` | Claude Code | comment/issue triggers |
| `claude-code-review.yml` | Claude Code Review | `pull_request`, `workflow_dispatch` |

## Core Workflows

### `python-check.yml` — CI

The primary PR gate. Runs on every pull request and via manual dispatch. Three jobs:

1. **Rust Checks** (`rust`) — `rustfmt`, `clippy`, and Rust parser checks (Python 3.11 to
   drive the build, with the Rust toolchain + cache).
2. **Code Quality & Unit Tests** (`code-quality`) — **matrix `['3.10', '3.11', '3.12']`**.
   Verifies `poetry.lock` is in sync with `pyproject.toml`, checks for stray debug flags,
   then runs code-quality checks and the unit-test suite (isort, black, flake8, mypy,
   bandit, pytest via the `run_checks` / taskipy tasks).
3. **Integration Tests** (`integration`) — builds the Rust parser and runs the integration
   suite (excluding tests that require a live Bitcoin node).

The README status badges (Code Quality, Rust Checks, Integration) point at the
corresponding jobs of this single workflow.

### `reparse-validate.yml` — Reparse Consensus Validation

Per-PR validation that the indexer's consensus surface still matches the checked-in
baseline (`indexer/snapshots/ci_consensus_hashes.json`). Triggered on PRs that touch
consensus-relevant paths (`index_core/**`, `rust_parser/**`, `config.py`, `pyproject.toml`,
`poetry.lock`, the snapshots, `ci/**`). Runs on the **matrix `['3.10', '3.11', '3.12']`**
and is **advisory** on first land (`continue-on-error: true`).

Three validation tiers (all run across the matrix):

- **Tier 1** — Cross-check `CHECKPOINTS_MAINNET` against `reference_hashes.json` (pure-Python
  AST parse; catches check.py / reference drift) for all baseline blocks.
- **Tier 2** — Block-bytes hash verification: each baseline block is fetched from a
  bitcoind RPC (or the public blockstream.info node) and its bytes verified against the
  expected `block_hash`.
- **Tier 3** — Full in-memory reparse (Rust parser + reparse pipeline) in a fresh
  subprocess per block, comparing `txlist_hash` / `messages_hash` / `ledger_hash` to the
  baseline. Tier 3 is DB-free, so blocks whose ledger depends on cross-block SRC-20 state
  (`TIER3_CROSS_BLOCK_LEDGER`) are excluded by design — they remain covered by Tiers 1–2
  and the periodic full stampsdev reindex (#775 / #778).

Also runs a **consensus package pin guard** (`ci/check_consensus_pkg_pins.py`) on each
matrix Python, proving consensus-critical packages (regex, PyNaCl, pybase64) resolve
identically on 3.10 / 3.11 / 3.12 (#759 / #803). Refresh the baseline with
`./indexer/ci/refresh-consensus-hashes.sh`.

### `freeze-drift.yml` — Freeze Drift Check

Verifies that the resolved Python packages **inside the production indexer Docker image**
match the checked-in baseline `indexer/ci/freeze.prod.lock` (built with `PYTHON_VERSION=3.12`).
`poetry.lock` guarantees lockfile-internal consistency but not what pip actually realizes
inside the prod image; this catches base-image/platform wheel drift (the regex / PyNaCl
drift in PR #753). Update the baseline intentionally with `./indexer/ci/refresh-freeze.sh`.

### `coverage.yml` — Coverage Analysis

Runs on PRs and pushes to `main`/`dev` (and manual dispatch). Executes the test suite under
coverage on **Python 3.11** (single version, matching integration tests) and uploads to
Codecov (`codecov.yml` / the codecov badge).

## Docker Workflows

### `docker-auto-publish.yml` — Docker Auto-Publish

On every push to `main`/`dev` that touches `indexer/**`, `docker/**`, or the workflow
itself, builds and pushes the indexer image (has `packages: write` permission). This is the
automated path that produces the `dev` and release images.

### `docker-publish.yml` — Docker Build and Publish

Manual (`workflow_dispatch`) build/publish with inputs: `tag` (required),
`environment` (`production` / `staging` choice), and optional `skip_tests`. When tests are
not skipped it runs the build/test jobs first, then builds a multi-arch image and pushes it.

## Versioning Workflows

### `version-check.yml` — Version Format Check

On pushes and PRs to `main`/`dev`, validates the version-string format for consistency.

### `bump-version.yml` — Bump Version

Automates version bumps. Triggers on pushes to `dev`/`main`, on closed PRs to those
branches, and manual dispatch with a `versionType` input (`major`/`minor`/`patch`/`build`/
`release`) and a `preRelease` flag. Uses Python 3.10.

## Reusable / Support Workflows

### `setup-python.yml` — Setup Python Environment

Reusable (`workflow_call`) workflow that installs Python, configures Poetry + dependencies,
builds the Rust parser, and caches dependencies. Consumed by other workflows.

### `build-test.yml` — Build Tests

Reusable (`workflow_call`) build + test verification (Python 3.10), invoked by the Docker
publish flow.

## Assistant Workflows

- **`claude.yml` — Claude Code**: responds to issue/PR comment triggers to run the Claude
  Code assistant against the repo.
- **`claude-code-review.yml` — Claude Code Review**: runs an automated Claude review on pull
  requests (and manual dispatch).

## Notes

- Consensus-critical changes are gated by `reparse-validate.yml` + `freeze-drift.yml` in
  addition to the standard `python-check.yml` CI; see `indexer/ci/README.md`.
- Sensitive credentials (Docker Hub, optional bitcoind RPC) are provided via GitHub Secrets.
