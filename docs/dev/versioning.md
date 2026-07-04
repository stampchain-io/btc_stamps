# Bitcoin Stamps Versioning & Release Guide

This document describes how versions and releases work for the Bitcoin Stamps
indexer. The repository follows a **trunk model**: **`main` is the single
primary branch** and the source of truth. Releases are **tag-driven** and cut by
maintainers with one manual workflow — you should almost never touch versions by
hand.

## Version format

`main` carries one of two states in its `VERSION` file (and its three mirrors —
see [Files the automation updates](#files-the-automation-updates)):

- **Between releases (normal state):** `MAJOR.MINOR.PATCH+dev.N` — e.g.
  `1.9.1+dev.0`. The base `X.Y.Z` is the **last shipped release**; `+dev.N` marks
  it as in-development. There is **no per-push version bump**, so `main` normally
  sits at `+dev.0` for the whole cycle.
- **A freshly cut release (momentary):** `MAJOR.MINOR.PATCH` — e.g. `1.10.0`.
  A release commit carries a clean `X.Y.Z` (**no `v` prefix**; the git tag is
  also `1.10.0`, not `v1.10.0`). Immediately after the release lands, `main` is
  reopened at `X.Y.Z+dev.0` for the next cycle.

`Version Format Check` CI (`.github/workflows/version-check.yml`) enforces that
`VERSION` is always either a clean `X.Y.Z` or the `X.Y.Z+dev.N` marker.

## Golden rules

1. **Branch off `main`; PRs target `main`.** There is no `dev` branch (it was
   retired and preserved as the `dev-archive` tag).
2. **Never** hand-edit the version carriers (`VERSION`, `indexer/pyproject.toml`,
   `indexer/src/config.py`, `.bumpversion.cfg`) — bumps are automated via
   `.bumpversion.cfg`.
3. **Never** push a version-bump commit directly to `main`. The `main-req`
   ruleset requires status checks on `refs/heads/main` with an empty bypass list,
   so a direct push of a version commit is rejected. Every version change flows
   through a PR + auto-merge (the Cut Release workflow does this for you).
4. **Releases are cut only by maintainers** via the **Cut Release** workflow
   (below). Release tags have **no `v` prefix**.

## `[skip-version]`

`[skip-version]` in a PR title documents that a PR must **not** trigger any
version automation. In the trunk model there is no per-push bump, so the only
version-changing PRs are the two automated ones the Cut Release workflow opens
(the release freeze and the reopen-at-`+dev.0` follow-up) — both are tagged
`[skip-version]` so no other automation acts on them. You do not normally add it
by hand.

## Cutting a release (the **Cut Release** workflow)

Releases are produced entirely by the `release.yml` **"Cut Release"** workflow —
a PR-then-tag flow that satisfies branch protection on `main` (a direct
version-bump push to `main` is rejected by the required-checks ruleset). A
maintainer triggers it manually:

> **Actions → Cut Release → Run workflow → choose bump = `major` | `minor` | `patch`**

What happens, hands-off, from there:

1. **`prepare`** — reads `main`'s `X.Y.Z+dev.0`, strips the `+dev.N` marker to
   recover the last released base, and applies the chosen bump to compute the
   clean target (`patch → 1.9.2`, `minor → 1.10.0`, `major → 2.0.0`). It creates
   `release/vX.Y.Z` off `main` with all version files frozen to `X.Y.Z`, opens a
   `[skip-version]` PR to `main`, and enables squash auto-merge. The PR merges
   once the required checks (including code-owner review) are green.
2. **`finalize`** (runs when that `release/*` PR squash-merges into `main`):
   - **tags `X.Y.Z`** (no `v` prefix) on the merge commit, pushed with the `PAT`
     so tag-triggered workflows fire (a tag pushed with the default token would
     not trigger downstream Actions);
   - creates the **`Release X.Y.Z`** GitHub Release (auto-generated notes);
   - opens a follow-up `[skip-version]` PR (branch `chore/reopen-X.Y.Z-dev`)
     that **reopens `main` at `X.Y.Z+dev.0`** for the next cycle, and
     auto-merges it. This PR's head is `chore/*` (not `release/*`), so it does
     not re-trigger `finalize`.
3. **`docker-auto-publish.yml`** — the `X.Y.Z` tag push triggers the release
   image build, which publishes `btcstamps/indexer:X.Y.Z` + `:latest` to Docker
   Hub, then **signs the image keyless and attaches an SPDX SBOM** (see
   [Verifying a signed release image](#verifying-a-signed-release-image)).

Example: a `minor` bump from `1.9.1+dev.0` produces tag `1.10.0`, Release
`1.10.0`, Docker `btcstamps/indexer:1.10.0` + `:latest`, and reopens `main` at
`1.10.0+dev.0`.

There is **no** manual "push a bump to main", "sync branches", or "force-push"
step — the trunk model has none of those.

## Between-release builds (pre-release images)

Every push to `main` (merged PRs) triggers `docker-auto-publish.yml`, which
publishes **staging-only** images:

- `btcstamps/indexer:edge` — a moving pointer to the newest `main` build.
- `btcstamps/indexer:sha-<short>` — the specific commit build (7-char SHA). Only
  the newest five `sha-*` tags are kept; older ones are pruned automatically.

Staging pushes **never** publish `:latest` or a clean `:X.Y.Z` tag, and they are
**not** signed. Merged Dependabot / feature PRs therefore reach `:edge`
immediately but **do not ship** to `:latest` / `:X.Y.Z` until a maintainer cuts a
tag.

## Verifying a signed release image

Release images are signed **keyless** (Sigstore/cosign via GitHub Actions OIDC —
no private keys) and carry an SPDX SBOM attestation. Each GitHub Release records
the exact `btcstamps/indexer@sha256:…` digest and the commands to verify it. The
signing identity is the release workflow running on the release tag:

```bash
# Verify the signature (substitute the release version and the digest from the
# Release notes):
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

`bump2version` (driven by `.bumpversion.cfg`) keeps four mirrored version
carriers in lockstep:

- `VERSION`
- `indexer/pyproject.toml`
- `indexer/src/config.py` (`VERSION_STRING`)
- `.bumpversion.cfg` (`current_version`)

The `X.Y.Z+dev.N` marker matches `config.py`'s `VERSION_STRING` parser
(`release="dev"`, `build=N`), so the minimum-version comparison in `check.py`
(which only looks at `MAJOR.MINOR.PATCH`) is unaffected.

## `bump2version` reference (maintainers / manual recovery only)

The Cut Release workflow uses an explicit `--new-version` (not a semantic part
bump) because `main`'s release-part value is `dev`, which is intentionally
outside `.bumpversion.cfg`'s bumpable set. You should not need these by hand.

```bash
bump2version --new-version X.Y.Z --no-tag --allow-dirty patch   # freeze a release
bump2version --new-version X.Y.Z+dev.0 --no-tag --allow-dirty patch   # reopen dev marker

# Options:
#   --new-version   set an exact version (e.g. 1.10.0 or 1.10.0+dev.0)
#   --no-tag        do NOT create a git tag (finalize tags separately)
#   --allow-dirty   allow uncommitted changes in the working tree
```

## Troubleshooting

- **Version format error in CI.** `VERSION` must be a clean `X.Y.Z` or the
  `X.Y.Z+dev.N` marker. If `main` is ever wrong, open a small `[skip-version]` PR
  that sets the four version carriers correctly.
- **Release didn't tag / publish.** Confirm the `release/*` PR actually
  squash-merged into `main` (that is what triggers `finalize`), then check the
  Cut Release run for the `finalize` job and the Docker Auto-Publish run for the
  tag build. Release tags must be pushed with the `PAT` for the downstream build
  to fire.
- **Reopen PR didn't auto-merge.** If auto-merge is unavailable, merge the
  one-file `chore: reopen development at X.Y.Z+dev.0 [skip-version]` PR by hand to
  restore the development marker on `main`.
