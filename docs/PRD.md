# Product requirements

## Problem and objectives

A project can stop working even when its code is unchanged. A runtime switches versions, a lockfile changes, a service stops, or a variable disappears from the process starting the application. Developers often have to reconstruct the last working state from shell history and diagnostic commands.

Drift lets developers save a working environment and see what changed when a project breaks. It should be quick to install, useful from a terminal and in local automation, independent of application frameworks, and practical across macOS, Linux, and Windows. The [CLI specification](CLI_SPEC.md) and [data model](DATA_MODEL.md) own the detailed contracts.

## Users and workflows

| User | What they can do |
| --- | --- |
| Application developer | Initialize a project, save a working snapshot with a short note, and retrieve it by ID. Compare the live environment against the latest or a selected snapshot when the project fails to start. |
| Teammate onboarding into a project | Inspect active runtime versions and distinguish environment variable names in the process from names declared in configured files. |
| Automation author | Verify a known-working baseline and distinguish drift, incomplete coverage, and command errors by exit code and JSON output. |
| Maintainer debugging an intermittent issue | Examine historical snapshots to find when a dependency checksum or local service state last differed. |

## Functional requirements

All requirements in this table are required for the MVP. The [implementation checklist](ROADMAP.md#implementation-checklist) maps them to deliverables and verification work.

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| FR-001 | Initialize local project configuration and storage idempotently. | A fresh project can be initialized twice. An existing configuration keeps its bytes and an interrupted initialization can be retried safely. |
| FR-002 | Observe OS, OS version, CPU architecture, and Python, Node.js, npm, PHP, Java, and Go versions. | Fixtures distinguish detected versions, missing executables, failed detection, and unsupported launchers. |
| FR-003 | Observe Docker installation, client and Compose versions, local daemon availability, and safe project service states. | Fixtures cover missing Docker, an unreachable daemon, and filtered service states for an explicitly configured project. |
| FR-004 | Track active environment variable names and declarations from explicitly configured files. | Changing only a variable value has no effect. Adding or removing names is observable independently in each source. Missing configured files are reported. |
| FR-005 | Track checksums of the standard dependency manifests and lockfiles. | A fixture can add, remove, and alter a listed file. The snapshot contains relative paths and checksums. |
| FR-006 | Record Git branch, commit, and working tree status as context. | Safe repositories report context, including detached or unborn states. Git-only changes leave verification unchanged. |
| FR-007 | Save uniquely identified, versioned snapshots with timestamps, optional messages, results, and statuses. | A partial capture saves and reads back correctly. Parallel captures keep independent IDs and records. |
| FR-008 | List historical snapshots and show a selected snapshot with metadata. | History has stable chronological order. Lookup resolves exact IDs and unique prefixes. Corrupt entries are surfaced. |
| FR-009 | Compare the current environment to the latest or a selected snapshot. | Added, removed, and modified observations are reported in stable order, and failed probes produce coverage gaps. |
| FR-010 | Set a known-working baseline and verify against it. | Verification distinguishes a match, drift, incomplete coverage, and a missing or invalid baseline. |
| FR-011 | Provide help, version information, JSON output, and non-interactive execution. | CLI contract tests cover flags, streams, error codes, and JSON payloads for every leaf command. |
| FR-012 | Distribute the CLI through PyPI, a Homebrew tap, and GitHub Releases. | Release builds produce a wheel and sdist. Fresh installs through uv, pipx, and the tap run the version and workflow smoke tests. |

## Non-functional requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| NFR-001 | Keep observations local and minimize sensitive data. | Sentinel secrets never appear in generated snapshots, output, or diagnostics. The CLI has no telemetry or upload path. |
| NFR-002 | Execute bounded, fixed observational probes. | Tests enforce argument arrays, supported launchers, time and output limits, local Docker scope, and safe Git behavior. |
| NFR-003 | Constrain filesystem access and protect local state. | Tests exercise traversal, symlinks, junctions, special files, restrictive permissions where supported, and default Git exclusion. |
| NFR-004 | Preserve consistent state through partial failure, interruption, and concurrent writes. | Injected failure and multiprocess tests verify atomic publication, no-clobber initialization, baseline integrity, and corruption reporting. |
| NFR-005 | Support Python 3.12+ across Linux, macOS, and Windows where practical. | The supported CI matrix passes and the documented platform gaps have explicit statuses. |
| NFR-006 | Keep Drift lightweight and maintainable. | The release passes Ruff, Mypy, Pytest, and artifact checks. The runtime dependency list stays focused on CLI, presentation, and validation. |
| NFR-007 | Produce deterministic machine-readable results. | Controlled repeated runs preserve ordering, schema shape, and outcome for equivalent normalized observations. |
| NFR-008 | Keep interactive diagnostics responsive. | The release records reproducible capture timings with typical fixtures and verifies the documented command and collector budgets with simulated stalls. |

## Success metrics

Track these during fixture runs and maintainer-led usability checks. Drift collects no usage analytics.

| Metric | MVP target |
| --- | --- |
| Time to first useful comparison | A developer can initialize, snapshot, and compare a prepared project in under two minutes using the README workflow. |
| Diagnostic accuracy | Acceptance fixtures report every planted change once and zero confirmed changes caused by failed probes. |
| Automation compatibility | Every documented verification outcome has a CLI test for its exit code and JSON payload. |
| Capture latency | Target a median under two seconds on a recorded reference machine with a small project and responsive probes. Report missing the target separately from violating a probe deadline. |

## Scope boundaries and future work

The MVP covers local observation, snapshots, comparison, baselines, human and JSON output, tests, documentation, and public packaging. Future Drift work may improve collector coverage and historical inspection through separately approved requirements.

Features outside the MVP are web dashboards, cloud synchronization, accounts, AI troubleshooting, automatic repairs, runtime or dependency installation, environment restoration, database backup, plugin marketplaces, remote monitoring, and integration with Seed, Relay, Capsule, or Rewind. Drift's product boundary is observation and comparison.

Drift is a standalone member of a proposed developer toolkit, with an independent repository, release lifecycle, and data model. Seed covers database seeding, Relay covers API recording and replay, Capsule covers reproducible workspaces, and Rewind covers local state recovery.

## Terminology

| Term | Meaning |
| --- | --- |
| Project root | Directory with `drift.toml`, or the directory targeted by initialization. |
| Collector | Module that observes one part of the environment. |
| Probe | An individually comparable check, such as the Node.js version or a dependency checksum. |
| Snapshot | Immutable, timestamped record of observations and collection statuses. |
| Baseline | Local pointer to a snapshot the developer has designated as working. |
| Drift | Confirmed difference between comparable observations. |
| Coverage gap | An observation the comparison could not establish on one or both sides. |
| Context | Information that helps interpret a snapshot, such as Git metadata. |
