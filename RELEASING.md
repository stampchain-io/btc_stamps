# Releasing btc_stamps

Releases are **automated** by [`.github/workflows/bump-version.yml`](.github/workflows/bump-version.yml).
Normally you do **nothing by hand** except merge the release PR and, afterward, merge the
auto-opened sync-back PR. This document explains the flow so it stays functional.

## Version model

- **`dev`** always carries a **canary** version: `X.Y.Z+canary.N`, where `X.Y.Z` is the
  **last released version** and `N` is an auto-incrementing build number. Every push to `dev`
  bumps `N` (`X.Y.Z+canary.N → X.Y.Z+canary.N+1`).
- **`main`** always carries a clean **release** version: `X.Y.Z` (no `+canary`), tagged `vX.Y.Z`.

The four files kept in lock-step (by `.bumpversion.cfg`): `VERSION`,
`indexer/pyproject.toml`, `indexer/src/config.py` (`VERSION_STRING`), `.bumpversion.cfg`.

## Cutting a release (the happy path)

1. Open a PR **`dev → main`**. Put the bump level in the **PR title**:
   - `[major]` → `X+1.0.0`
   - `[minor]` → `X.Y+1.0`
   - _(neither)_ → patch `X.Y.Z+1`
2. **Squash-merge** it (merge commits are disabled repo-wide). On merge, the workflow's
   **"Handle PR merge to main"** step runs automatically and:
   1. **Strips canary** — `X.Y.Z+canary.N → X.Y.Z` (`bump2version ... --no-tag release`).
      This lands on the *previous* release version, so it must **not** tag (see pitfall below).
   2. **Applies the bump** from the PR title → e.g. `X.Y.Z → X.Y+1.0`, which **commits and
      creates the `vX.Y+1.0` tag**.
   3. Pushes `main` + the new tag, publishes the **GitHub Release**, and builds/pushes the
      **Docker images** (`btcstamps/indexer:X.Y+1.0` + `:latest`).
   4. Opens a **sync-back PR `main → dev`**.
3. **Merge the sync-back PR.** The **"Handle PR merge to dev"** step converts the release
   version back to canary: `X.Y+1.0 → X.Y+1.0+canary.1`. Development resumes on the new line.

### End state (correctly aligned)
- `main`: `X.Y+1.0`, tag `vX.Y+1.0`, GitHub Release + Docker images published.
- `dev`: `X.Y+1.0+canary.1`, and each subsequent push increments the canary build number.

## `[skip-version]` escape hatch

Put `[skip-version]` in a commit message (or PR title) to make the workflow **skip** all
version manipulation for that merge — used for hotfixes to the version files themselves.

## Pitfall this doc exists to prevent (2026-07 incident)

The canary-strip in step 2.1 lands on the **already-released** previous version (`X.Y.Z`),
whose tag `vX.Y.Z` already exists. If that `bump2version release` is run **without
`--no-tag`**, it tries to re-create `vX.Y.Z` and dies with
`fatal: tag 'X.Y.Z' already exists`, aborting the entire release — `main` is left on the
canary string, no new tag, no Release, and Docker publishes the wrong (canary) version.

**Fix / invariant:** the canary-strip **must** use `--no-tag`; only the title-driven bump in
step 2.2 creates a tag. The `main → dev` step already follows this rule. Do not remove it.

## Manual recovery (if the auto-bump ever fails again)

If `main` is stuck on a `+canary` string after a release merge:
1. Branch off `main`, set all four version files to the intended `X.Y+1.0`, commit with
   `[skip-version]`, open a PR to `main`, and squash-merge it.
2. Tag and push: `git tag vX.Y+1.0 <merge-sha> && git push origin vX.Y+1.0`.
3. Create the GitHub Release for `vX.Y+1.0` (attach curated notes).
4. Confirm the Docker publish ran for `X.Y+1.0`/`:latest` (re-run the job if it fired on the
   canary version).
5. Open + merge the `main → dev` sync-back PR to restore `X.Y+1.0+canary.1` on `dev`.
