# Bitcoin Stamps Versioning Guide

This document outlines the versioning processes for the Bitcoin Stamps project, particularly focusing on managing versions between development (dev) and production (main) branches.

## Version Format

- Main branch: `MAJOR.MINOR.PATCH` (e.g., `1.8.26`)
- Dev branch: `MAJOR.MINOR.PATCH+canary.BUILD` (e.g., `1.8.26+canary.1`)

## Command Breakdown

### bump2version Command Format
```bash
bump2version [part] [options]

# Common parts:
# - release: Switch between prod/canary formats
# - minor: Increment minor version (1.8.26 → 1.9.0)
# - patch: Increment patch version (1.8.26 → 1.8.27)
# - major: Increment major version (1.8.26 → 2.0.0)
# - build: Increment canary build (1.8.26+canary.1 → 1.8.26+canary.2)

# Common options:
# --new-version: Specify exact version or format (prod/canary)
# --allow-dirty: Allow uncommitted changes in working directory
```

## Branch Synchronization Workflows

### 1. Starting New Development Work (Main → Dev)

To sync dev with main's latest changes:

```bash
# 1. Create a PR from main to dev
# You can do this via GitHub UI or command line:
git checkout main
git pull origin main
git checkout dev
git pull origin main
git push origin dev
# Then create PR from main to dev via GitHub UI
```

The GitHub Action will automatically:
1. Detect that it's a PR from main to dev
2. Convert the version to canary format
3. Update all version files
4. Create appropriate tags

Example:
- Starting version: `1.8.26`
- After PR merge: `1.8.26+canary.1`

Note: No need to manually run any version commands - the workflow handles everything!

### 2. Making Dev Changes

The GitHub Action will automatically:
1. Check if version is in canary format
2. If in canary format, increment the build number
3. Update all version files and create tags

Example progression:
```
1.8.26+canary.1 → 1.8.26+canary.2 → 1.8.26+canary.3
```

### 3. Creating PR to Main

When creating a PR from dev to main:

#### Default Behavior (Automatic Patch Bump)
By default, when merging to main:
1. Keep the version in canary format
2. The GitHub Action will automatically:
   - Convert canary version to prod format
   - Bump the patch version
   - Update version files
   - Create appropriate tags

Example:
- PR version: `1.8.26+canary.5`
- After merge: `1.8.27`

#### Version Control via PR Title
You can control version bumping using keywords in the PR title:
- `[minor]`: Will bump minor version instead of patch
- `[major]`: Will bump major version instead of patch
- `[skip-version]`: Will skip version bump entirely

Example PR titles:
- "feat: add new feature [minor]" → `1.8.26+canary.5` → `1.9.0`
- "fix: bug fix" → `1.8.26+canary.5` → `1.8.27` (default patch bump)
- "feat: breaking change [major]" → `1.8.26+canary.5` → `2.0.0`
- "chore: update deps [skip-version]" → `1.8.26+canary.5` → `1.8.26`

### 4. Manual Version Updates

For cases requiring manual version control:

```bash
# Using workflow_dispatch:
# Go to Actions → Bump Version → Run workflow
# Select version type: major, minor, patch, build, or release
# Optionally mark as pre-release

# Or using command line:
bump2version [type] --allow-dirty
git push origin HEAD --tags
```

Note: When using manual version control, add `[skip-version]` to your PR title to prevent automatic version bumping.

### 5. Syncing Dev After Main Update

After main has been updated with version bumps (typically after merging a PR from dev to main):

```bash
# 1. Switch to dev and fetch latest from both branches
git switch dev
git fetch origin main dev

# 2. Rebase dev onto the latest main to include version updates
git rebase origin/main

# 3. Force push the updated dev branch
git push -f origin dev

# The GitHub Action will automatically:
# - Convert to canary format
# - Create appropriate tags
```

Example:
- Starting version: `1.9.0`
- After sync: `1.9.0+canary.1`

This workflow is necessary after every PR merge from dev to main because:
1. The automated workflow creates version-bump commits on main
2. These version updates need to be properly synchronized back to dev
3. Using rebase keeps the git history clean and prevents branch divergence

## GitHub Actions Workflow Behavior

The workflow (`bump-version.yml`) handles:

1. PR Merge to Main:
   - Converts canary version to prod format
   - Applies version bump based on PR title
   - Updates version files
   - Creates appropriate tags

2. PR Merge to Dev:
   - Converts to canary format if merging from main
   - Creates appropriate tags
   - Updates version files

3. Dev Branch Commits:
   - Increments build number if in canary format
   - Updates version files
   - Creates appropriate tags

4. Manual Version Updates:
   - Supports manual version bumping via workflow_dispatch
   - Allows specifying version type (major, minor, patch, build, release)

## Files Updated

The workflow automatically updates these files:
- VERSION
- indexer/pyproject.toml
- indexer/src/config.py

## Best Practices

1. Let the GitHub Action handle format conversions
2. Use PR title keywords to control version bumping
3. Use `[skip-version]` when manual control is needed
4. Always ensure changes are committed before version updates

## Common Issues and Solutions

1. **Version Format Mismatch**
   - The workflow automatically handles format conversions
   - No need to manually convert between prod/canary formats

2. **Failed CI Workflows**
   - Ensure all changes are committed
   - Use `--allow-dirty` flag for manual updates

3. **Sync Issues**
   - Let the workflow handle version conversions during syncs
   - Manual intervention only needed for special cases

## Version Control Keywords

### PR Title Keywords
When creating a Pull Request, use these keywords in the PR title to control version bumping:
- `[minor]` - Bumps minor version
- `[major]` - Bumps major version
- `[skip-version]` - Skips version update for this PR

Note: For PRs, only the PR title is checked for keywords. Commit messages within the PR are ignored.

### Commit Message Keywords
For direct commits to branches (not through PRs):
- `[skip-version]` - Skips version update for this specific commit

Example:
```bash
# Direct commit to dev - will skip version bump
git commit -m "chore: update deps [skip-version]"

# PR to main - will bump minor version regardless of commit messages
git commit -m "feat: new feature [skip-version]"  # [skip-version] is ignored
git push origin dev
# Create PR with title: "feat: new feature [minor]"
```

## Process Flows

### 1. Normal PR to Main
```bash
# Create PR with title based on change type:
"feat: new feature"              # Will bump patch
"feat: new feature [minor]"      # Will bump minor
"feat: new feature [major]"      # Will bump major
"chore: update [skip-version]"   # Won't bump version

# Result:
# - Workflow checks PR title only
# - Ignores commit messages within PR
# - Applies version bump based on PR title
```

### 2. Direct Commits to Dev
```bash
# Regular commit - will bump canary build
git commit -m "feat: your changes"
git push origin dev

# Skip version bump
git commit -m "chore: quick fix [skip-version]"
git push origin dev

# Result:
# - Workflow checks commit message
# - Skips version bump if [skip-version] is present
```

## Important Notes

1. **PR Version Control**
   - Only PR titles control version bumping
   - Commit messages within PRs are ignored
   - PR title keywords: `[major]`, `[minor]`, `[skip-version]`

2. **Direct Commit Version Control**
   - Only affects direct pushes to branches
   - Only `[skip-version]` is checked
   - Applies to that specific commit only

3. **Process Safety**
   - PR merges always use PR title for version control
   - Direct commits can be skipped individually
   - No mixing of PR and commit message controls

4. **Best Practices**
   - Use PR titles to control major/minor version bumps
   - Use commit `[skip-version]` for maintenance commits
   - Keep version control intent clear in PR titles
