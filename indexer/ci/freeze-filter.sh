#!/usr/bin/env bash
# Filter `pip freeze` output down to the indexer's PRODUCTION runtime closure as
# resolved by poetry.lock — i.e. exactly the packages that
# `poetry install --without dev` installs at locked versions.
#
# Why this exists: the freeze-drift baseline is dumped from the Dockerfile
# `builder` stage (indexer/Dockerfile), which `pip install`s the poetry +
# maturin BUILD toolchain into the same site-packages as the project deps. An
# unfiltered `pip freeze` therefore captured two kinds of noise:
#
#   1. poetry's entire transitive closure that is NOT in poetry.lock at all
#      (anyio, httpx, httpcore, h11, cleo, dulwich, CacheControl, RapidFuzz,
#      keyring, ...). These are unpinned and flap (e.g. anyio 4.14.0<->4.14.1)
#      on nearly every CI run.
#   2. poetry/maturin tooling deps that DO appear in poetry.lock but only in the
#      `dev` group (virtualenv, maturin, distlib, platformdirs, ...). Because the
#      prod build uses `--without dev`, poetry does NOT pin these — their
#      installed versions come from `pip install poetry==... maturin==...` and
#      drift independently of the lock (e.g. virtualenv 20.36.1 locked vs
#      20.39.1 installed).
#
# Both classes made the Freeze Drift Check chronically red even when no
# production dependency had moved. Keeping only the non-dev (main + arweave +
# any future non-dev group) poetry.lock packages restricts the check to what the
# indexer actually runs and what poetry pins, so drift means a REAL
# production-dependency change — the signal the check was built to catch (#753).
#
# Both the generation side (refresh-freeze.sh) and the verification side
# (.github/workflows/freeze-drift.yml) pipe through THIS script, so the baseline
# and the live dump are always filtered identically.
#
# Usage:
#   pip freeze --all --exclude-editable | freeze-filter.sh path/to/poetry.lock
set -euo pipefail

LOCK="${1:?usage: freeze-filter.sh path/to/poetry.lock}"
if [ ! -f "$LOCK" ]; then
  echo "freeze-filter.sh: poetry.lock not found at: $LOCK" >&2
  exit 1
fi

# PEP 503-ish normalization: lowercase and fold '.'/'_' to '-'. Applied
# identically to both the poetry.lock names and the pip-freeze package names so
# the two sides compare apples-to-apples.
norm() { tr 'A-Z' 'a-z' | tr '._' '--'; }

# Names of every poetry.lock package whose group set includes at least one
# non-dev group (i.e. the prod runtime install set under `--without dev`).
names="$(
  awk '
    /^\[\[package\]\]/        { name=""; keep=0 }
    /^name = "/               { line=$0; sub(/^name = "/,"",line); sub(/".*$/,"",line); name=line }
    /^groups = /              { g=$0; gsub(/"dev"/,"",g); if (g ~ /"[^"]+"/) keep=1 }
    /^files = / && name != "" { if (keep) print name; name=""; keep=0 }
  ' "$LOCK" | norm | LC_ALL=C sort -u
)"

while IFS= read -r line; do
  [ -z "$line" ] && continue
  # Drop the locally-built Rust wheel: its sha256 is not byte-reproducible until
  # #759 Item 2 (wheel distribution) lands; its version lives in Cargo.toml.
  case "$line" in
    btc[_-]stamps[_-]parser*) continue ;;
  esac
  pkg="${line%%==*}"
  pkg="$(printf '%s' "$pkg" | norm)"
  if grep -qxF -- "$pkg" <<<"$names"; then
    printf '%s\n' "$line"
  fi
done | LC_ALL=C sort
