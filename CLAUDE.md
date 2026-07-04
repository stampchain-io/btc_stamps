# Bitcoin Stamps Indexer — Claude Guide

Indexer for the Bitcoin Stamps protocol (SRC-20/SRC-721/STAMP). A **Rust transaction
parser** (`indexer/src/rust_parser/`, PyO3 module `btc_stamps_parser`) feeds the Python
ledger engine (`indexer/src/index_core/`). All commands run from `indexer/`.

## Dev vs prod — READ FIRST
- **Dev** = this docker stack at `/home/ubuntu/stampsdev/btc_stamps` (branch `dev`).
  Containers `btc_stamps-indexer-1` + `btc_stamps-mysql-1` (MySQL 8.4 @ `127.0.0.1:3306`,
  db `btc_stamps`). `RDS_*` env = the dev MySQL.
- **Prod** = systemd service at `/home/ubuntu/btc_stamps` (Aurora MySQL). `ST3_*` env =
  PROD Aurora (read-only compares only). **NEVER** touch/restart/reindex/write prod or `ST3_*`.
- **Shared infra:** `bitcoind` + `counterparty-core` (`/home/ubuntu/counterparty-core`) are
  shared with prod. Never stop/restart them; keep RPC load modest.
- A long from-genesis reindex may be running in the dev docker stack. Stay read-only of
  `db_data/`, `reindex_capture.log`, and compose files unless told otherwise.
- **Python:** prod runs 3.10, dev container 3.12, `pyproject` `^3.10`. Consensus is
  provably invariant across 3.10–3.12 (audited #803; CI runs the 3.10/3.11/3.12 matrix).

## Build / test / lint (validate exactly as CI)
```bash
cd /home/ubuntu/stampsdev/btc_stamps/indexer
poetry install
poetry run task build           # build Rust ext (release); task build-dev = debug. Rerun if lib.rs/*.rs changed.

# Linters (what CI runs; --check/--check-only forms):
poetry run isort . --check-only
poetry run black --check . --config=pyproject.toml
poetry run flake8 src/ --count --statistics
poetry run mypy src/ --explicit-package-bases
poetry run task bandit          # bandit -r src/ tests/ tools/ -s B608 -lll

# Unit suite as CI runs it (~2 min, ~1870 tests):
PYTHONPATH=src USE_TEST_TX_HEX=1 TESTING=1 USE_TEST_DB=1 MOCK_DB=1 CI_FIXTURE_MODE=true \
  poetry run pytest -n auto -m "not requires_bitcoin_node and not integration"
```
- One-shot wrapper for the whole code-quality gate (lint + Rust build + unit tests):
  `poetry run check-code`. Linters-only: `poetry run lint` (`--auto-fix` fixes isort/black).
- black/isort/flake8/mypy line length = 127; flake8 ignores E203,W503,E402,E501,C901,E704.
- Single test: `poetry run pytest tests/test_x.py -v`. Markers in `pyproject` /
  `tests/README.md` (`integration`, `requires_bitcoin_node`, `requires_db`, …).

## CI gates (`.github/workflows/`)
- **CI** (`python-check.yml`): Rust checks + Code Quality & Unit Tests on 3.10/3.11/3.12 +
  Integration (no bitcoind). `poetry check --lock` must pass.
- **Reparse Consensus Validation** (`reparse-validate.yml`, 3.10/3.11/3.12) — the
  output-neutrality proof for any consensus-path change. 3 tiers over baseline
  `indexer/snapshots/ci_consensus_hashes.json` (~78 blocks):
  - Tier 1 cross-check `CHECKPOINTS_MAINNET` (`index_core/check.py`) vs `reference_hashes.json`.
  - Tier 2 block-bytes hash verification (all baseline blocks).
  - Tier 3 DB-free in-memory reparse (txlist/messages/ledger hashes) over self-contained
    blocks only; `TIER3_CROSS_BLOCK_LEDGER` blocks are excluded by design (their
    `ledger_hash` needs prior SRC-20 state) and covered by the full reindex instead.
  - Local Tier 3: `poetry run python ci/ci_reparse_subprocess.py --limit 5`, or one block
    `poetry run python ci/smoke_parser_validation.py --block N` (uses public backend; no bitcoind).
- **Freeze Drift** (`freeze-drift.yml`): realized prod-image packages vs `indexer/ci/freeze.prod.lock`.
  Consensus-critical pins (regex/PyNaCl/pybase64) also guarded by `ci/check_consensus_pkg_pins.py`.
- The **full from-genesis stampsdev reindex** is the final pre-release consensus gate and
  owns SRC-20 cross-block `ledger_hash`. User-triggered only — never start it unprompted.

## Consensus model (the load-bearing invariant)
- Three rolling hashes: **txlist_hash / ledger_hash / messages_hash**. Any change on the
  decode/filter/parse path must be **output-neutral** OR **flag-gated, default OFF**, and
  proven by Reparse Consensus Validation green (txlist+ledger identical).
- Test/CI backend substitution uses the **backend injection seam** (`set_backend_override` /
  `clear_backend_override`, or env `BTC_STAMPS_BACKEND_OVERRIDE="module:Class"`), refs
  #800/#802. NEVER reassign `backend_instance` per-module — modules import `Backend` by
  value and a miss silently hits real bitcoind. `conftest.py::reset_backend_override`
  (autouse) clears it between tests.

## Conventions
- Branch off `dev`; PRs base `dev`, set milestone (e.g. `v1.9.0`) + labels
  (`consensus`/`ci`/`perf`/`supply-chain`/`documentation`). `v1.9.0` cuts via long-running
  PR #495 (`dev`→`main`).
- Version bumps are automated (`.bumpversion.cfg`, canary scheme `1.8.x+canary.N`) — do not
  hand-edit `VERSION`/`pyproject` version/`config.py:VERSION_STRING`.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
  PR body footer: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Gotchas / do-NOT
- **Never `git add -A`** — stage explicitly. Untracked handoff/scratch/`.env.local*` files
  and `indexer/tools/debug/*.py` get swept in otherwise.
- **Test pollution:** suite runs `pytest -n auto`; several tests `importlib.reload(config)`.
  Tests touching `config` must resolve it at call-time and `monkeypatch` values — never rely
  on a module-level `import config` (goes stale after reload).
- **`FORCE` mode** bypasses ONLY the SRC-20 ledger balance hash; it still halts on
  txlist/stamp divergence — it is NOT a consensus override.
- Flaky CI (re-run, not real failures): `Code Coverage Analysis` (live-backend RPC/SIGABRT)
  and `Integration Tests` (hits live `api.counterparty.io`, intermittent 503); `freeze-drift`
  can time out pulling the base image. `gh run rerun <run-id>`.
- Never decide release-level things autonomously: #755 activation height, flipping
  `CP_SKIP_NO_COUNTERPARTY_BLOCKS` on, cutting #495, or running the reindex — PARK for the user.

## Orientation (where things live)
- `indexer/src/index_core/` — ledger engine: `blocks.py`, `backend.py`, `transaction_utils.py`,
  `check.py` (checkpoints), `src20.py`/`src101.py`/`src721.py`, `stamp.py`, `block_validation.py`,
  `reparse/` (validator + snapshot).
- `indexer/src/rust_parser/src/` — `lib.rs`, `arc4.rs`, `constants.rs`.
- `indexer/ci/` — consensus/CI runners + guards. `indexer/snapshots/` — baselines.
- `indexer/tools/` — ops/debug (`compare_tables.py`, `checkpoint_updater.py`, …).
- Docs: `docs/ARCHITECTURE.md`, `PROTOCOLS.md`, `DATABASE.md`, `DEVELOPMENT.md`;
  project state in `HANDOFF.md` + `AUTONOMOUS_OVERNIGHT_HANDOFF.md`.
