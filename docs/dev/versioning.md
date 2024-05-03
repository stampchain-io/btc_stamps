# Bitcoin Stamps Versioning

Minor versions are handled automatically through GitHub Actions based upon
commits to the dev or main branch.

## Patch Version Update

For patch version updates, the GitHub Action workflow checks out the code from
the repository, sets up Python 3.9, and installs the necessary dependencies,
including bump2version.

If the code is pushed to the dev branch, the workflow runs the
`bump2version build` command, which increments the build part of the version
number. The new version number is stored in the `VERSION` file.

If the code is pushed to the main branch, the workflow runs the
`bump2version minor --serialize "v{major}.{minor}.{patch}"` command, which
increments the minor version number and resets the patch version number. The new
version number is stored in the `VERSION` file.

After bumping the version, the workflow commits the changes, creates a git tag
with the new version number, and pushes the changes and the new tag to the
repository.

## Major Version Update

For major version updates which contain breaking updates to the prior release
the process is manual. To release a new major version, follow these steps:

1. Run the `bump2version major` command locally.
2. Push the changes and the new tag to the repository using
   `git push origin main --tags`.

## Versioning Workflow

Trigger: The workflow is triggered whenever code is pushed to the main or dev
branches.

Environment Setup: The workflow runs on the latest version of Ubuntu. It checks
out the code from the repository and sets up Python 3.9.

Dependency Installation: It then installs the necessary dependencies, which in
this case is bump2version, a Python library for version bumping.

Version Bumping and Tag Creation: The workflow then checks which branch the code
was pushed to. If the code was pushed to the dev branch, it runs the
`bump2version build` command to increment the build part of the version number.
If the code was pushed to the main branch, it runs the
`bump2version minor --serialize "v{major}.{minor}.{patch}"` command to increment
the minor version number and reset the patch version number. The new version
number is stored in the `VERSION` file.

Push Changes: The workflow then configures the git user name and email, and
pushes the changes and the new tag to the repository.

Release Creation: Finally, the workflow creates a new GitHub release with the
new version number. The release is created as a draft, and is marked as a
pre-release if the code was pushed to the dev branch.

## Versioning Workflow Example

Commit to dev branch: When you commit to the dev branch, the GitHub Action will
trigger. It will increment the build part of the version number. For example, if
the current version is `v1.0.0+canary.0`, after the commit, the version will be
`v1.0.0+canary.1`. A new git tag `v1.0.0+canary.1` will be created and pushed to
the repository.

Commit to main branch: When you commit to the main branch, the GitHub Action
will trigger. It will increment the minor version number and reset the patch
version number. For example, if the current version is v1.0.0+canary.1, after
the commit, the version will be v1.1.0. A new git tag v1.1.0 will be created and
pushed to the repository.

Commit to dev branch again: After the commit to the main branch, when you commit
to the dev branch again, the GitHub Action will increment the build part of the
version number. For example, if the current version is v1.1.0, after the commit,
the version will be v1.1.0+canary.0. A new git tag v1.1.0+canary.0 will be
created and pushed to the repository.

Manual Major Version Update: To release a new major version, run the
`bump2version major` command locally. Then, push the changes and the new tag to
the repository using `git push origin main --tags`.
