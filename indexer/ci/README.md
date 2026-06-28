# `indexer/ci/`

CI helpers for the indexer. Tooling here exists to keep what ships in the
production Docker image byte-for-byte aligned with what maintainers run locally,
because the indexer's stamp / SRC-20 / CP detection logic is consensus-critical.

## `freeze.prod.lock`

Sorted output of `pip freeze --all --exclude-editable` from inside the
production indexer image (`indexer/Dockerfile` with `INSTALL_DEV=false`,
Python 3.12), narrowed by `freeze-filter.sh` (below) to the production runtime
closure — i.e. the `poetry.lock` packages that `poetry install --without dev`
actually pins (the `main` + `arweave` groups). This is the canonical record of
every third-party resolved package version that the indexer actually runs.

The `builder` stage `pip install`s the poetry + maturin BUILD toolchain into the
same site-packages as the project deps, so a raw `pip freeze` also captured
poetry's transitive closure — packages either absent from `poetry.lock`
(`anyio`, `httpx`, `httpcore`, `h11`, `cleo`, `dulwich`, `CacheControl`,
`RapidFuzz`, `keyring`, ...) or present only in its `dev` group
(`virtualenv`, `maturin`, `distlib`, `platformdirs`, ...). poetry does not pin
those for prod, so their installed versions drifted independently of the lock
and flapped the check on nearly every PR (e.g. `anyio` 4.14.0 <-> 4.14.1).
Filtering to the non-`dev` `poetry.lock` groups removes that noise while keeping
full coverage of the real runtime deps (including the consensus-critical
`regex` / `PyNaCl` / `pybase64` guarded by `check_consensus_pkg_pins.py`).

The Rust parser is excluded because the wheel it builds is not byte-
reproducible across runs even with a pinned toolchain (different sha256
each time). Its version is tracked separately in
`indexer/src/rust_parser/Cargo.toml`. Once #759 Item 2 (wheel distribution
from a pinned release artifact) lands, we can re-include it.

Why this file and not just `poetry.lock`: `poetry.lock` guarantees lockfile-
internal consistency, but it does NOT guarantee that `pip install` inside the
prod base image produces the same versions a maintainer has on their laptop.
Base-image wheel preferences, Python minor differences, and platform tags can
all diverge. The empirical bug in PR #753 (regex 2024.11.6 vs 2026.2.28, PyNaCl
1.5.0 vs 1.6.2) was exactly this class of drift. Pinning the realized state
catches the next one before it merges.

The `.github/workflows/freeze-drift.yml` check rebuilds the prod image on every
PR that touches `pyproject.toml`, `poetry.lock`, or `Dockerfile` and fails if
the resulting `pip freeze` differs from this file.

## Updating the baseline

Run the refresh script whenever you intentionally change a dep, bump the
lockfile, or modify the Dockerfile:

```bash
./indexer/ci/refresh-freeze.sh
git add indexer/ci/freeze.prod.lock
git diff --cached indexer/ci/freeze.prod.lock   # sanity check what moved
git commit
```

The script builds the prod-mode image, dumps `pip freeze --all` inside it, pipes
it through `freeze-filter.sh`, and sorts the result. It takes ~5–10 minutes on a
cold cache, ~1 minute warm.

If you see a surprise version change in the diff, treat it as a real signal —
that's the whole point. Investigate before committing the new baseline.

## `refresh-freeze.sh`

The script invoked above. Builds `indexer/Dockerfile` with `--target builder`
(stops before the runtime stage; we only need site-packages) and tags the
result `btc-stamps-freeze-baseline:tmp`. Override the Python minor with
`PYTHON_VERSION=3.11 ./indexer/ci/refresh-freeze.sh` if you ever need to
generate a baseline against a different interpreter.

## `freeze-filter.sh`

Shared filter used by BOTH `refresh-freeze.sh` (baseline generation) and
`.github/workflows/freeze-drift.yml` (live verification), so the two sides are
always filtered identically. Reads `pip freeze` on stdin and a `poetry.lock`
path as its argument, and emits only the packages whose `poetry.lock` group set
includes a non-`dev` group — the production runtime closure that
`poetry install --without dev` pins. Also drops the locally-built
`btc_stamps_parser` wheel. See the `freeze.prod.lock` section above for why the
unfiltered dump was chronically flapping the check.
