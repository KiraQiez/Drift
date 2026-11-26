# CLI specification

Drift is non-interactive. Each invocation targets one project, emits one report or error, and exits. JSON fields and exit codes in this document are part of the v1 CLI contract.

## Syntax and project selection

```text
drift [--project PATH] COMMAND
drift --help
drift --version

drift init [--json]
drift snapshot [-m MESSAGE | --message MESSAGE] [--json]
drift history [--json]
drift diff [SNAPSHOT] [--json]
drift show SNAPSHOT [--json]
drift baseline set SNAPSHOT [--json]
drift verify [--json]
```

Place the global `--project` option before the command. It accepts an absolute path or a path relative to the working directory and selects an existing directory exactly. Without it, `init` targets the working directory. Other commands search upward for the nearest directory containing `drift.toml`, including the working directory itself, and stop at the filesystem root. A nearer invalid configuration is an error rather than a reason to continue searching. Commands requiring initialized state also validate the local Drift directory.

`SNAPSHOT` is a full canonical ID or an unambiguous prefix of six or more lowercase hex characters. Resolve against canonical storage names and reject ambiguous prefixes. Use the full ID when automating. The [data model](DATA_MODEL.md) defines ID format, reference resolution, and storage recovery.

`--help` is available at the root, the `baseline` group, and each command. Calling the root or `baseline` group without a subcommand displays help with exit `0`. `--version` reports `drift <version>` and exits `0`. Help and version handling are independent of project state.

## Commands and acceptance criteria

| Command | Behavior and acceptance |
| --- | --- |
| `init` | Create the project configuration and local state described in the [data model](DATA_MODEL.md#storage-and-recovery). Preserve an existing valid configuration byte for byte. Repeating successful initialization performs no writes. An interrupted initialization can create missing state on retry, subject to existing state validation. An invalid configuration or unsafe path fails with guidance. |
| `snapshot` | Capture live observations, assign an ID and UTC timestamp, and publish one immutable snapshot. Accept one optional literal message with 1–256 characters and no control characters. Save partial or failed collection results with their statuses. Return success once the snapshot is saved. Storage errors return exit `1`. |
| `history` | List summaries oldest first, using ID to break timestamp ties. Empty history is a successful empty result. If a canonical entry is unreadable, show valid entries, identify each damaged entry, and exit `4`. |
| `diff` | Resolve a specified reference or select the newest snapshot by the same ordering used for history. Collect current observations without creating a snapshot. Return changes, coverage gaps, and Git context. Missing history, an invalid selected snapshot, or unreadable history during automatic latest selection is an operational error. |
| `show` | Return the selected snapshot with its full stored metadata, scope, observations, and statuses. Unknown, ambiguous, damaged, and unsupported references receive distinct application errors. |
| `baseline set` | Validate the selected snapshot and atomically set the pointer. The caller may designate a snapshot with partial observations. Repeating the same selection succeeds without changing the pointer. An invalid reference leaves the previous pointer in place. |
| `verify` | Read the configured baseline, validate its snapshot, and compare the live environment with the same comparison behavior as `diff`. Return a clear match, drift, or incomplete report with the documented exit code. Missing or damaged baseline state is an operational error. |

## Output

Human reports go to stdout and fatal diagnostics go to stderr. Render IDs, timestamps, statuses, and changes in readable text or tables. Show the affected probe and reason for coverage gaps. Present Git as context. Use plain text on non-TTY streams and render external strings as literal text. No command prompts for input.

A plain-text verification report could look like this.

```text
Drift detected against a81f23d4901649b1aa477f030a879e44
Modified  runtime.node  20.18.0 → 22.12.0
Coverage gap  runtime.java  current probe timed out
```

`--json` emits one UTF-8 JSON object and a final newline on stdout, with no styling or auxiliary output. A result has `schema_version` equal to `1`, a `command` string using the leaf command name (including `baseline set`), and a `result` object. A handled application error uses `error` in place of `result`, with a stable `code` and a human-readable `message`. CLI usage errors use stderr, with fixed diagnostics for invalid snapshot references and messages. Help and version use their ordinary text. Machine consumers should branch on the exit code or error code.

| Command | Fields in `result` |
| --- | --- |
| `init` | `created` is true if the invocation created managed project state or configuration, false if the project was already initialized. |
| `snapshot` | `snapshot` is a snapshot summary. |
| `history` | `snapshots` is an array of summaries. `damaged` is an array of objects with `id` and `code`, sorted by ID. |
| `show` | `snapshot` is the full v1 snapshot. |
| `baseline set` | `baseline_id` is the full selected ID. |
| `diff`, `verify` | `reference_id` is the full ID. `outcome` is `match`, `drift`, or `incomplete`. `changes` and `gaps` follow the [data model](DATA_MODEL.md#json-schema-v1). `warnings` contains `no_comparable_observations` when applicable. `git` contains the `reference` and `current` Git collector results. |

A snapshot summary exposes `id`, `created_at`, nullable `message`, and `collector_statuses`, a mapping from collector ID to aggregate status. Empty arrays remain present. History entries use `invalid_snapshot`, `unsupported_schema`, `unsafe_path`, or `storage_error` for damaged snapshot codes.

Example `drift verify --json` result with drift and a coverage gap.

```json
{
  "schema_version": 1,
  "command": "verify",
  "result": {
    "reference_id": "a81f23d4901649b1aa477f030a879e44",
    "outcome": "drift",
    "changes": [
      {
        "collector": "runtime",
        "probe": "node",
        "subject": null,
        "kind": "modified",
        "before": "20.18.0",
        "after": "22.12.0"
      }
    ],
    "gaps": [
      {"collector": "runtime", "probe": "java", "side": "current", "code": "timeout"}
    ],
    "warnings": [],
    "git": {
      "reference": {"status": "disabled", "probes": {}},
      "current": {"status": "disabled", "probes": {}}
    }
  }
}
```

Example application error.

```json
{
  "schema_version": 1,
  "command": "verify",
  "error": {
    "code": "baseline_missing",
    "message": "Set a baseline with drift baseline set SNAPSHOT."
  }
}
```

## Exit codes and errors

| Exit | Meaning |
| --- | --- |
| `0` | Successful operation, help or version, or complete comparison with no drift. |
| `1` | Operational error. A required project, reference, or local state could not be resolved, read, validated, or written. |
| `2` | CLI usage error, including an invalid flag, missing argument, malformed reference syntax, or invalid message. |
| `3` | At least one confirmed environment change, including comparisons that also have gaps. |
| `4` | Comparison is incomplete without confirmed drift, or history is partial because at least one canonical entry is unreadable. |

Report `project_not_initialized` when no project configuration can be located, `invalid_config` for unreadable or invalid configuration, and `unsafe_path` for path safety violations. An invalid explicit project directory uses `invalid_project`. An empty history on implicit comparison uses `history_empty`. Use `snapshot_not_found`, `ambiguous_snapshot`, and `invalid_snapshot` for reference errors, and `unsupported_schema` when a well-formed integer version is unsupported. Automatic latest selection with unreadable entries uses `history_incomplete`. Use `baseline_missing` for an unset baseline and `invalid_baseline` for a set pointer whose target is missing, unreadable, or invalid. Use `storage_error` for state I/O or invalid metadata, and `internal_error` for unexpected application failures. Keep messages actionable and omit raw inputs or underlying exception text.

## Examples

```sh
drift --project ./my-project init
cd ./my-project
drift snapshot -m "Working environment"
drift history --json
drift show a81f23
drift diff
drift diff a81f23 --json
drift baseline set a81f23
drift verify
```

The sample prefix stands for a unique ID prefix in the local history.
