# Roadmap and implementation checklist

The collector engine foundation is complete. The next implementation task is **T-005**. A task is eligible once its listed dependencies are complete.

## Milestones

| Phase | Tasks | Deliverables and exit criteria |
| --- | --- | --- |
| [1. Project foundation](#phase-1-project-foundation) | T-001–T-002 | Local repository and Python package, help and version entry point, quality recipes, and validated project configuration and path access. Exit when the locked foundation checks pass. |
| [2. Collector engine](#phase-2-collector-engine) | T-003–T-007 | Bounded runner and six collectors with normalized results. Exit when missing, unsafe, failed, and successful observations are distinguishable in fixtures. |
| [3. Snapshot and storage engine](#phase-3-snapshot-and-storage-engine) | T-008–T-011 | Versioned storage, idempotent initialization, capture, history, and show. Exit when fixtures prove round-trip, interruption, corruption, and parallel capture behavior. |
| [4. Comparison engine](#phase-4-comparison-engine) | T-012–T-013 | Pure deterministic comparison and the live diff command. Exit when confirmed changes, scope changes, and coverage gaps are correctly presented in both output formats. |
| [5. Baseline and verification](#phase-5-baseline-and-verification) | T-014–T-015 | Atomic baseline selection and automation-friendly verification. Exit when all baseline outcomes and exit codes are exercised through the CLI. |
| [6. Production readiness](#phase-6-production-readiness) | T-016–T-018 | End-to-end tests, cross-platform CI, and security and latency review. Exit when required gates pass and platform limitations are documented. |
| [7. Packaging and public release](#phase-7-packaging-and-public-release) | T-019–T-023 | Final identities, verified artifacts and install paths, trusted release workflows, and a Homebrew tap. Exit when an approved version can be installed from all supported channels. |

Public release depends on a distinct distribution name and maintainer-controlled GitHub and tap identities. See [release identity](RELEASE.md#release-identity).

## Implementation checklist

`P0` covers core or safety work. `P1` covers other required MVP work. Requirement IDs refer to the [PRD](PRD.md#functional-requirements). Mark a task complete when its acceptance criteria and applicable [quality gates](DEVELOPMENT.md#quality-gates-and-ci) are verified. Record the evidence with the task.

### Phase 1. Project foundation

- [x] **T-001 · Establish the repository and package** · P0
  - **Dependencies** None
  - **Requirements** `FR-011`, `NFR-005`, `NFR-006`
  - **Deliverable** Local Git initialization, Python `src` package, provisional metadata and console entry point, lockfile, license, ignore rules, Just recipes, and initial tests.
  - **Complete when** A locked setup runs help, version, quality checks, and a local build.
  - **Verified** On macOS arm64, `just setup`, `just check`, and `just build` passed on Python 3.12.16. All four CLI tests also passed on Python 3.14.8. Fresh installs from the wheel and sdist both passed help and version checks from an empty directory.
- [x] **T-002 · Load configuration and constrain project paths** · P0
  - **Dependencies** `T-001`
  - **Requirements** `FR-001`, `FR-004`, `FR-011`, `NFR-003`
  - **Deliverable** Root resolution, strict TOML loading, and shared safe-path access.
  - **Complete when** Fixtures cover defaults, overrides, invalid configs, traversal, links, and ambiguous paths.
  - **Verified** On macOS arm64, `just check`, `just build`, and all 55 tests passed with Python 3.12.16. All 55 tests also passed with Python 3.14.8. Tests exercised descriptor-relative and fallback reads, including symlinks, FIFOs, and a symlink substitution during descriptor-based opening. Native Windows junction coverage remains part of the platform checks.

### Phase 2. Collector engine

- [x] **T-003 · Run bounded typed probes** · P0
  - **Dependencies** `T-002`
  - **Requirements** `FR-002`, `FR-007`, `NFR-001`, `NFR-002`, `NFR-004`, `NFR-008`
  - **Deliverable** The collector contract, registry, scheduler, and shared subprocess runner.
  - **Complete when** Timeouts, overflow, failed commands, missing launchers, and unexpected collector errors yield isolated, sanitized results.
  - **Verified** On macOS arm64, Ruff, Mypy, and the package build passed. Python 3.12.16 and 3.14.8 each passed 74 tests, with one native Windows launcher test skipped. Tests covered process reaping, inherited pipes, the combined output cap, environment filtering, missing launchers, and collector failure isolation.
- [x] **T-004 · Collect system and runtime data** · P0
  - **Dependencies** `T-003`
  - **Requirements** `FR-002`, `NFR-002`, `NFR-005`
  - **Deliverable** The system collector and six runtime probes.
  - **Complete when** Fixtures verify normalized metadata, absent tools, version formats, and supported and unsupported launcher handling.
  - **Verified** Ruff, Mypy, and 78 tests passed on macOS with Python 3.12. One Windows-only test was skipped. Fixtures covered Windows npm layout checks, runtime failure classification, and normalized versions.
- [ ] **T-005 · Collect environment names and dependency checksums** · P0
  - **Dependencies** `T-002`, `T-003`
  - **Requirements** `FR-004`, `FR-005`, `NFR-001`, `NFR-003`, `NFR-007`
  - **Deliverable** Name-only collection, a declaration scanner, and bounded checksum probes.
  - **Complete when** Value-only edits leave results stable, file and active names stay distinct, and checksums and failures match fixtures.
- [ ] **T-006 · Observe local Docker and scoped services** · P1
  - **Dependencies** `T-003`
  - **Requirements** `FR-003`, `NFR-001`, `NFR-002`, `NFR-005`
  - **Deliverable** Docker client, local daemon, Compose, and explicit project service probes.
  - **Complete when** Mocked commands distinguish tool absence, daemon absence and failure, and emit only allowed fields for the selected project.
- [ ] **T-007 · Collect safe Git context** · P1
  - **Dependencies** `T-003`
  - **Requirements** `FR-006`, `NFR-001`, `NFR-002`
  - **Deliverable** Root-local Git repository, branch, commit, and worktree data.
  - **Complete when** Clean, dirty, detached, and unborn cases are covered and unsafe repository configuration cannot trigger hooks, filters, or network operations.

### Phase 3. Snapshot and storage engine

- [ ] **T-008 · Implement typed local storage and atomic publication** · P0
  - **Dependencies** `T-002`, `T-003`
  - **Requirements** `FR-001`, `FR-007`, `FR-008`, `NFR-001`, `NFR-003`, `NFR-004`, `NFR-007`
  - **Deliverable** The v1 snapshot and metadata model, safe JSON access, ID resolution, and atomic create and replace operations.
  - **Complete when** Strict validation, collision handling, interrupted writes, and reader consistency work in fixtures and concurrent processes.
- [ ] **T-009 · Initialize project state** · P0
  - **Dependencies** `T-008`
  - **Requirements** `FR-001`, `FR-011`, `NFR-003`, `NFR-004`
  - **Deliverable** The `init` command and state bootstrap.
  - **Complete when** Repeated and concurrent calls preserve existing bytes, partial setup can be retried, and local state is ignored by default.
- [ ] **T-010 · Capture snapshots** · P0
  - **Dependencies** `T-004`, `T-005`, `T-006`, `T-007`, `T-008`, `T-009`
  - **Requirements** `FR-007`, `FR-011`, `NFR-001`, `NFR-004`
  - **Deliverable** Capture orchestration and the `snapshot` command.
  - **Complete when** A normal or partial capture writes exactly one immutable record and parallel invocations produce separate valid IDs.
- [ ] **T-011 · List and inspect history** · P0
  - **Dependencies** `T-008`, `T-010`
  - **Requirements** `FR-008`, `FR-011`, `NFR-004`, `NFR-007`
  - **Deliverable** `history` and `show`.
  - **Complete when** History ordering is stable, exact and unique-prefix lookups work, and mixed histories retain readable results with the specified exit code.

### Phase 4. Comparison engine

- [ ] **T-012 · Compare normalized observations** · P0
  - **Dependencies** `T-008`, `T-010`
  - **Requirements** `FR-006`, `FR-009`, `NFR-007`
  - **Deliverable** The pure comparator and typed change and gap records.
  - **Complete when** Change types, scope mismatches, confirmed absence, unknown observations, and Git context follow the data contract.
- [ ] **T-013 · Expose live comparison** · P0
  - **Dependencies** `T-010`, `T-011`, `T-012`
  - **Requirements** `FR-009`, `FR-011`, `NFR-007`
  - **Deliverable** The `diff` command with reports and exit codes.
  - **Complete when** Default latest and explicit reference paths work, damage blocks automatic selection, and comparisons leave storage untouched.

### Phase 5. Baseline and verification

- [ ] **T-014 · Set a known-working baseline** · P0
  - **Dependencies** `T-008`, `T-011`
  - **Requirements** `FR-010`, `FR-011`, `NFR-004`
  - **Deliverable** `baseline set` with atomic metadata publication.
  - **Complete when** Valid references set the pointer, failed writes preserve readable metadata, and concurrent readers and writers observe valid pointers.
- [ ] **T-015 · Verify the live environment** · P0
  - **Dependencies** `T-013`, `T-014`
  - **Requirements** `FR-010`, `FR-011`, `NFR-007`
  - **Deliverable** `verify` over the shared comparison service.
  - **Complete when** Match, drift, incomplete, missing and damaged baseline, and drift with gaps produce the specified outputs and exit codes.

### Phase 6. Production readiness

- [ ] **T-016 · Verify complete workflows and public contracts** · P0
  - **Dependencies** `T-015`
  - **Requirements** `FR-001`, `FR-007`, `FR-008`, `FR-009`, `FR-010`, `FR-011`, `NFR-007`
  - **Deliverable** Integration coverage from initialization through verification.
  - **Complete when** Each leaf command and result shape is checked with isolated projects and controlled probe inputs.
- [ ] **T-017 · Run locked cross-platform CI** · P1
  - **Dependencies** `T-001`, `T-016`
  - **Requirements** `NFR-005`, `NFR-006`
  - **Deliverable** The GitHub Actions quality matrix.
  - **Complete when** The minimum and current supported Python versions pass on Linux, macOS, and Windows, with capability-specific cases documented.
- [ ] **T-018 · Complete the privacy, filesystem, and latency review** · P0
  - **Dependencies** `T-006`, `T-007`, `T-016`, `T-017`
  - **Requirements** `NFR-001`, `NFR-002`, `NFR-003`, `NFR-004`, `NFR-005`, `NFR-008`
  - **Deliverable** Platform evidence for safety cases and timed fixture runs.
  - **Complete when** The sentinel and scope tests pass, probe bounds are verified, and remaining limitations and measured latency are recorded.

### Phase 7. Packaging and public release

- [ ] **T-019 · Resolve release identities** · P1
  - **Dependencies** `T-001`
  - **Requirements** `FR-012`
  - **Deliverable** A maintainer-approved distribution name, GitHub identity, and tap identity with collision checks.
  - **Complete when** The installation examples and publish targets reflect verified ownership and naming choices.
- [ ] **T-020 · Validate distributable artifacts** · P1
  - **Dependencies** `T-017`, `T-018`, `T-019`
  - **Requirements** `FR-012`, `NFR-005`, `NFR-006`
  - **Deliverable** The build and installer smoke workflow.
  - **Complete when** Wheel and sdist metadata, contents, hashes, and clean installs pass on the supported platforms.
- [ ] **T-021 · Prepare PyPI and GitHub release automation** · P1
  - **Dependencies** `T-019`, `T-020`
  - **Requirements** `FR-012`, `NFR-006`
  - **Deliverable** Tag validation, changelog handling, the scoped Trusted Publisher workflow, and GitHub Release artifact delivery.
  - **Complete when** The approved staging path exercises build, validation, and publication controls.
- [ ] **T-022 · Prepare the Homebrew tap** · P1
  - **Dependencies** `T-019`, `T-020`
  - **Requirements** `FR-012`, `NFR-005`
  - **Deliverable** The formula, dependency resource update process, and tap validation.
  - **Complete when** A candidate formula can install and run the CLI smoke test on a supported macOS runner.
- [ ] **T-023 · Publish and verify the first approved release** · P1
  - **Dependencies** `T-021`, `T-022`
  - **Requirements** `FR-012`
  - **Deliverable** An approved tag, GitHub Release, PyPI package, and tap formula.
  - **Complete when** The published artifacts match recorded hashes and clean installs through uv tool, pipx, and Homebrew pass.
