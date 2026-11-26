# Release and distribution

## Release identity

| Surface | Release identity |
| --- | --- |
| Project | Drift (Development Environment Version Control) |
| PyPI and application installers | `drift-dev-env` |
| Python import and console command | `drift` |
| GitHub repository | `KiraQiez/Drift` |
| Homebrew tap and formula | `KiraQiez/homebrew-tap` and `drift` |

The `drift` PyPI name belongs to an existing project. The Phase 7 collision checks found no PyPI project under the normalized `drift-dev-env` name or Homebrew core formula named `drift`. The repository maintainer controls the `KiraQiez` GitHub namespace. The distribution name and tap path will be claimed as part of first-release setup. [Existing PyPI project](https://pypi.org/project/drift/)

Development builds use version `0.1.0.dev0`. The first public release targets `0.1.0`.

```sh
brew install KiraQiez/tap/drift
uv tool install drift-dev-env
pipx install drift-dev-env
```

These are planned installations from the project's own tap and PyPI package. Each installer manages the application's Python environment.

## Artifacts and versioning

Build a wheel and sdist with Hatchling through `uv build`. Package the `src` code and console script along with runtime dependency declarations, the README, and the Apache 2.0 license. Keep development tools, temporary projects, and local Drift state out of release packages. Verify file contents and metadata for both artifact types. Smoke-install the exact artifacts that will ship, then calculate and record their SHA-256 digests.

Use SemVer and a matching Git tag of the form `vMAJOR.MINOR.PATCH`. Use `0.1.0` as the starting target for the first public release. Check that the tag, package metadata, and CLI version agree. Record user-visible changes, fixes, compatibility notes, and manual upgrade steps in a maintained changelog. Persisted schema versions follow the separate [data model](DATA_MODEL.md#json-schema-v1).

## Release pipeline

```mermaid
flowchart LR
    Tag["Approved version tag"] --> Quality["Locked quality and platform checks"]
    Quality --> Build["Build wheel and source distribution"]
    Build --> Validate["Validate artifacts and smoke-install"]
    Validate --> PyPI["Publish to PyPI with a Trusted Publisher"]
    Validate --> GitHub["Attach artifacts and hashes to GitHub Release"]
    PyPI --> Tap["Update formula and dependency resources"]
    GitHub --> Final["Verify public downloads and clean installs"]
    Tap --> Final
```

Run quality checks for pull requests and again on every release tag. Pin workflow actions to reviewed commit SHAs. The publish workflow consumes the validated artifacts from the tagged commit. Grant `id-token: write` to the PyPI publish job only and configure the Trusted Publisher against the chosen repository, workflow, and protected release environment. Isolate GitHub Release asset permissions to the release job. Exercise the publication workflow through an authorized staging path before the first public release. [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) · [PyPI security model](https://docs.pypi.org/trusted-publishers/security-model/)

Publish release notes, the validated wheel and sdist, and checksums on GitHub Releases. After PyPI publication, the tap formula uses the published sdist and its digest. Pin a supported versioned Homebrew Python and use its Python virtual environment helper. Generate transitive runtime dependency resources with `brew update-python-resources`, review each resource version and source checksum, and declare the build resources required by the backend where necessary. Run formula validation, installation, and the formula test on a supported macOS runner before merging the tap update. [Homebrew language-specific formulae](https://docs.brew.sh/Language-Specific-Formulae)

## Publication validation and rollback

Verify version and help, initialization, a snapshot and baseline, and a fixture-driven comparison through the installed console command. Validate uv tool and pipx installs from the public package, and install the tap formula on a clean macOS runner. Compare the downloaded artifact digests to the release record. Sign off on the release only after each channel returns the expected version and exit codes.

If a stage fails, record the completed steps and resume the missing stage with the already validated artifacts. If a published package is broken, document the impact, revert the tap to the last working formula where applicable, and publish a corrected release with a new version. Yank a broken PyPI release when appropriate and provide a reason. Record the fix and recovery steps in the GitHub release notes and changelog. Preserve snapshot compatibility when publishing a fix and test any future migration independently. [PyPI yanking](https://docs.pypi.org/project-management/yanking/)
