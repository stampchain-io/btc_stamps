# Contributing

Thanks for contributing to the Bitcoin Stamps indexer. This is **consensus-critical**
software — please read the consensus rule below before opening a PR.

## Getting started

- Read [`CLAUDE.md`](CLAUDE.md) (dev vs prod, the consensus model, gotchas) and
  [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) / [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- A Rust transaction parser (`indexer/src/rust_parser/`, PyO3 module `btc_stamps_parser`)
  feeds the Python ledger engine (`indexer/src/index_core/`). **All commands run from
  `indexer/`.**

```bash
cd indexer
poetry install
poetry run task build        # build the Rust extension (release); task build-dev = debug
```

## Build / test / lint (validate exactly as CI does)

```bash
# Linters (CI runs the --check forms):
poetry run isort . --check-only
poetry run black --check . --config=pyproject.toml
poetry run flake8 src/ --count --statistics
poetry run mypy src/ --explicit-package-bases
poetry run task bandit       # bandit -r src/ tests/ tools/ -s B608 -lll

# Unit suite as CI runs it:
poetry run task test-unit    # pytest -m "not integration" (CI also excludes requires_bitcoin_node)

# One-shot gates:
poetry run lint              # all linters (poetry run lint --auto-fix fixes isort/black)
poetry run check-code        # lint + Rust build + unit tests
```

## The consensus rule (load-bearing)

Three rolling hashes define consensus: **`txlist_hash` / `ledger_hash` / `messages_hash`**.
Any change on the decode/filter/parse path MUST be:

- **output-neutral** (the three hashes are provably identical), **OR**
- **flag-gated and default OFF**,

and proven by **Reparse Consensus Validation green (txlist + ledger identical)**. Locally:
`poetry run python ci/ci_reparse_subprocess.py --limit 5`. Cross-block SRC-20 `ledger_hash`
is owned by the full from-genesis reindex (maintainer-triggered).

**Consensus-adjacent dependency bumps.** Some dependencies sit on the parse path and
can move the hashes: pip `msgpack` / `cryptography` / `ecdsa` / `pycryptodome` /
`pybase64` / `python-bitcoinlib` / `bitcoinlib`, and the entire cargo `rust_parser`
tree (`pyo3`, `rand`, `bitcoin`). Dependabot isolates these into their own PRs (the
`consensus-critical` pip group and the `cargo` entry in
[`.github/dependabot.yml`](.github/dependabot.yml)). **Do not auto-merge them** — they
must pass the Reparse Consensus gate first, get the `consensus` label, and are never
merged mid-release (they change release scope). A pip bump that touches
`indexer/poetry.lock` also needs `./indexer/ci/refresh-freeze.sh` re-run, or Freeze
Drift CI fails.

## Pull requests

- **Branch off `dev`; PRs target `dev`** (not `main`). Every PR is reviewed by two
  code owners (see [`.github/CODEOWNERS`](.github/CODEOWNERS)). **Releases are cut by
  maintainers** via the automated **Cut Release** workflow (PR-then-tag → signed
  `X.Y.Z` Docker image + GitHub Release → version-only sync-back to `dev`); do not
  open release PRs to `main` yourself. See [`docs/dev/versioning.md`](docs/dev/versioning.md).
- Title convention: `type(#NNN): summary` (e.g. `fix(#812): ...`, `chore: ...`).
- Set a **milestone** (e.g. `v1.9.0`) and **labels**
  (`consensus` / `ci` / `perf` / `supply-chain` / `documentation`).
- **Stage files explicitly — never `git add -A`** (scratch/debug/`.env.local*` files get
  swept in otherwise).
- **Do not hand-edit** `VERSION` / `pyproject` version / `config.py:VERSION_STRING` —
  version bumps are automated (`.bumpversion.cfg`).
- Fill out the [pull request template](.github/PULL_REQUEST_TEMPLATE.md); open issues with
  the [issue templates](.github/ISSUE_TEMPLATE/).

## Security

Do **not** file public issues for security, consensus-divergence, or supply-chain problems.
See [`SECURITY.md`](SECURITY.md) for private reporting.

By participating you agree to our [Code of Conduct](CODE_OF_CONDUCT.md).
