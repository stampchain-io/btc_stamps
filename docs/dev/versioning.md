# Bitcoin Stamps Versioning & Release Guide

This document describes how versions and releases work for the Bitcoin Stamps
indexer. **`dev` is the primary branch**; `main` carries the current production
release. Releases are **tag-driven** and cut by maintainers with a single manual
workflow — you should almost never touch versions by hand.

## Version Format

- **Main branch (production):** `MAJOR.MINOR.PATCH` — e.g. `1.9.0`
  (**no `v` prefix**; git tags are also `1.9.0`, not `v1.9.0`).
- **Dev branch (canary):** `MAJOR.MINOR.PATCH+canary.BUILD` — e.g. `1.9.0+canary.1`

Version Format Check CI enforces this: `dev` must be `+canary`, `main` must not.

## Golden rules

1. **Branch off `dev`; PRs target `dev`** (not `main`).
2. **Never** hand-edit `VERSION` / `indexer/pyproject.toml` /
   `indexer/src/config.py` — bumps are automated via `.bumpversion.cfg`.
3. **Never** push a bump commit directly to `main`, **never** rebase/force-push
   `dev` onto `main`, and **never** open a `main → dev` PR. (Why: this repo
   squash-merges `dev → main`, so `main` is a single squashed commit while `dev`
   keeps full history — a `main → dev` merge phantom-conflicts on every squashed
   commit and can never merge, and a rebase would rewrite `dev`'s protected
   history and break every open PR and clone.)
4. **Releases are cut only by maintainers** via the **Cut Release** workflow
   (below). Tags have **no `v` prefix**.

## Dev canary versioning (automated)

`bump-version.yml` runs on pushes/merges to `dev` and keeps the canary build
number moving. You don't run anything:

```
1.9.0+canary.1 → 1.9.0+canary.2 → 1.9.0+canary.3 …
```

### `[skip-version]` — opting a change out of a bump

- **On a PR merged to `dev`:** put `[skip-version]` in the **PR title** to skip
  the canary bump for that merge.
- **On a direct push to `dev`:** put `[skip-version]` in the **commit message**
  to skip the bump for that commit.

Only the PR title is inspected for PR merges (commit messages inside the PR are
ignored); only the commit message is inspected for direct pushes. No git tags or
GitHub Releases are created for dev/canary builds.

## Cutting a release (the **Cut Release** workflow)

Releases are produced entirely by the `release.yml` **"Cut Release"** workflow —
a PR-then-tag flow that satisfies branch protection on `main` (a direct
version-bump push to `main` is rejected by the required-checks ruleset). A
maintainer triggers it manually:

> **Actions → Cut Release → Run workflow → choose bump = `major` | `minor` | `patch`**

What happens, hands-off, from there:

1. **`prepare`** — computes the clean `X.Y.Z` from `main`'s current version and
   the chosen bump, creates `release/vX.Y.Z` off `main` with the version files
   set to `X.Y.Z` (prod), opens a `[skip-version]` PR to `main`, and enables
   squash auto-merge. It merges once the required checks are green.
2. **`finalize`** (runs when that release PR squash-merges into `main`):
   - **tags `X.Y.Z`** (no `v` prefix) on the merge commit, pushed with the `PAT`
     so tag-triggered workflows fire;
   - creates the **`Release X.Y.Z`** GitHub Release (auto-generated notes);
   - opens a **version-only sync-back PR** to `dev` setting it to
     `X.Y.Z+canary.1` (`[skip-version]` in the title) and auto-merges it, so
     canary development resumes on the new line. Only the version number syncs —
     `dev` already contains all of `main`'s code.
3. **`docker-auto-publish.yml`** — the `X.Y.Z` tag push triggers the release
   image build, which publishes `btcstamps/indexer:latest` + the clean
   `:X.Y.Z` tag to Docker Hub, then **signs the image and attaches an SBOM**
   (see below).

Example: a `minor` bump from `1.9.0` produces tag `1.10.0`, Release `1.10.0`,
Docker `btcstamps/indexer:1.10.0` + `:latest`, and syncs `dev` to
`1.10.0+canary.1`.

There is **no** manual "push a bump to main", "rebase dev onto main", or
"force-push" step — those legacy rituals are gone.

## Verifying a signed release image

Release images are signed **keyless** (Sigstore/cosign via GitHub Actions OIDC —
no private keys) and carry an SPDX SBOM attestation. Each GitHub Release records
the exact `btcstamps/indexer@sha256:…` digest and the commands to verify it:

```bash
# Verify the signature (substitute the digest from the Release notes):
cosign verify \
  --certificate-identity-regexp '^https://github.com/stampchain-io/btc_stamps/.github/workflows/docker-auto-publish.yml@refs/tags/X.Y.Z$' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  btcstamps/indexer@sha256:<digest>

# Verify the SPDX SBOM attestation:
cosign verify-attestation --type spdxjson \
  --certificate-identity-regexp '^https://github.com/stampchain-io/btc_stamps/.github/workflows/docker-auto-publish.yml@refs/tags/X.Y.Z$' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  btcstamps/indexer@sha256:<digest>
```

## Files the automation updates

- `VERSION`
- `indexer/pyproject.toml`
- `indexer/src/config.py`

## `bump2version` reference (for maintainers / manual recovery only)

```bash
bump2version [part] [options]

# Parts:
#   major   1.9.0 → 2.0.0
#   minor   1.9.0 → 1.10.0
#   patch   1.9.0 → 1.9.1
#   build   1.9.0+canary.1 → 1.9.0+canary.2
#   release switch prod <-> canary serialization

# Options:
#   --new-version   set an exact version (e.g. 1.9.0+canary.1)
#   --no-tag        do NOT create a git tag (required for canary + strip steps)
#   --allow-dirty   allow uncommitted changes in the working tree
```

**Invariant:** any `bump2version release` that lands on an already-released
`X.Y.Z` **must** use `--no-tag`, or it re-creates that tag and aborts. The Cut
Release workflow already does this; only override it during manual recovery.

## Troubleshooting

- **Version format error in CI.** `dev` must be `X.Y.Z+canary.N`, `main` must be
  clean `X.Y.Z`. The automation normally keeps these correct; if a branch is
  wrong, open a small `[skip-version]` PR that sets the version files correctly.
- **Sync-back PR didn't auto-merge.** If auto-merge is unavailable, just merge
  the one-file `chore: sync dev to X.Y.Z+canary.1 …` PR by hand to restore
  canary versioning on `dev`.
- **Release aborted with `tag 'X.Y.Z' already exists`.** Manual recovery: branch
  off `main` → set the version files to the intended `X.Y.Z` → open a
  `[skip-version]` PR to `main` → merge → `git tag X.Y.Z <sha> && git push origin
  X.Y.Z` → create the GitHub Release → confirm Docker published `X.Y.Z` / `latest`
  → let the sync-back PR restore canary on `dev`.
- **Legacy canary tags/Releases.** Old `X.Y.Z+canary.N` git tags or Releases are
  cruft and safe to delete; real release tags (`X.Y.Z`) must be kept.
