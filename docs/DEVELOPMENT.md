# Development guide

## Commands

Run these commands from the repository root. Use the locked development environment for local checks and CI. Track the uv lockfile in Git and update it when dependencies change.

| Command | Purpose | Invocation |
| --- | --- | --- |
| `just setup` | Sync the development environment | `uv sync --locked` |
| `just test` | Run Pytest | `uv run --locked pytest` |
| `just format` | Apply Ruff formatting | `uv run --locked ruff format .` |
| `just lint` | Check lint and formatting | `uv run --locked ruff check .` and `uv run --locked ruff format --check .` |
| `just typecheck` | Check application types | `uv run --locked mypy src` |
| `just check` | Run the quality gates | Run the lint, typecheck, and test recipes |
| `just build` | Build the wheel and source distribution | `uv build` |

## Engineering standards

Follow the shared [contribution rules](../RULES.md) for coding, commits, and verification. Use this guide for development commands and test expectations.

## Test structure and fixtures

Use Pytest to exercise public behavior and core invariants. Default runs use temporary projects and synthetic inputs, independent of production credentials, external APIs, a running Docker daemon, and changes to the developer's tools or environment.

| Location | What it covers |
| --- | --- |
| `tests/unit/` | Configuration and schema validation, probe parsers and normalization, collector deadlines, ID resolution and ordering, and pure comparison logic. |
| `tests/integration/` | CLI parsing, output and exit codes, file permissions, storage recovery, concurrent writes, and fixture workflows across commands. |
| Release jobs | Wheel and sdist contents, installs from each artifact or distribution channel, and smoke runs of the installed CLI. |

Build temporary projects with `tmp_path`. Pass controlled environments to tests and replace external command execution at the bounded runner seam. Use synthetic stdout, stderr, return codes, and timeouts. For tests of the runner itself, use short-lived Python children or fixed local fixtures that simulate the expected behavior. Use a fixed clock and IDs for ordering tests, and real separate processes for storage concurrency. Keep platform-specific cases explicit so missing coverage is visible.

## Acceptance matrix

| Area | Required scenarios |
| --- | --- |
| Initialization and config | Fresh and repeated initialization, preservation of pre-existing bytes, interrupted setup and retry, upward discovery, explicit project selection, nested invalid configuration, unknown settings, unsafe paths, and invalid TOML or schema versions. |
| Tool probes | Missing runtimes, malformed version output, unsupported launchers, Docker missing or present with an unavailable daemon, local endpoint selection, configured service filtering, timeout, output overflow, and a failure isolated to one collector. |
| Files and environment | Each manifest path, content changes, absent files, a file changing during hashing, environment values changing with names unchanged, allowlist filtering, missing environment files, multiline quoted values, invalid syntax, and Windows key case. |
| Git context | Clean and dirty trees, detached and unborn HEAD, absent Git, unsupported checkout layout, filters and hooks never invoked, and Git-only differences excluded from drift. |
| Snapshot data and storage | Round-trip serialization, UTC formatting, strict schemas, wrong or duplicate keys, unsupported versions, snapshot ID and filename mismatch, prefix collisions, parse failure, partial snapshots, corrupt metadata, and corruption in mixed histories. |
| Concurrency and interruption | Parallel initialization, simultaneous captures, colliding snapshot IDs, interruption before publication, abandoned staging files, races between readers and publishers, and concurrent baseline updates. |
| Comparison and verification | Added, removed, and modified observations, stable ordering, known absence versus failed probes, changed coverage scope, partial coverage with and without drift, no comparable observations, missing baseline, invalid target, and no writes during comparison. |
| CLI | Every leaf command, help and version without a project, invalid usage, non-TTY output, stable JSON keys and streams, and exit codes `0` through `4`. |
| Security | Sentinel secrets in input values, command output, and errors. Unsafe binaries, traversal, symlinks, Windows junctions, special files, remote Docker settings, terminal escapes, and private POSIX permissions. |
| Packaging | Install both wheel and sdist in fresh isolated environments. Verify the console script, version, help, initialization, and a snapshot-to-verification flow against fixture input. |

Prefer meaningful branch and failure-mode coverage over an aggregate percentage. Each required CLI outcome, comparison rule, and write consistency guarantee needs a direct assertion. A happy-path smoke test is insufficient evidence for a timeout, security boundary, or concurrent write.

## Quality gates and CI

Run Ruff, Mypy, and Pytest before completing an implementation task. Report which checks passed and give a reason for checks that were skipped or unavailable.

The [quality workflow](../.github/workflows/quality.yml) runs on Linux, macOS, and Windows with CPython 3.12 and 3.15. It runs for pushes and pull requests targeting `main` or `staging`, and for version tags. Each job uses the locked development dependencies, runs Ruff, Mypy, and pytest, and builds the package. Pytest reports skipped cases by capability, such as POSIX permissions or Windows-only junctions.

Use fixture timings and simulated stalls to assess the [responsiveness target](PRD.md#success-metrics). Test artifacts and installers through the [release process](RELEASE.md#publication-validation-and-rollback).

Run `uv run --locked python scripts/measure_capture.py` to measure capture locally. The workflow records the median and maximum of seven installed CLI snapshots in a temporary project with two manifests, one dotenv file, and the current Python executable. It disables Docker and Git for this fixture. The median target is two seconds. The timing reports target misses separately from functional failures, and the runner tests verify deadline and output enforcement with simulated stalls.

### Phase 6 capture timings

Median seconds for seven captures per hosted job.

| Runner | Architecture | Python 3.12 | Python 3.15 |
| --- | --- | ---: | ---: |
| Linux | x86-64 | 0.146 | 0.184 |
| macOS | arm64 | 0.288 | 0.210 |
| Windows | x86-64 | 0.337 | 0.250 |

All six medians met the two-second target. The fixture measures process startup, responsive collectors, and snapshot publication on the hosted runners. [Timing and test logs](https://github.com/KiraQiez/Drift/actions/runs/45788789851)
