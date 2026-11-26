# Data model

The MVP uses UTF-8 JSON for local state and TOML for project configuration. Pydantic validates the versioned models on write and on read. The [CLI specification](CLI_SPEC.md) owns command envelopes and exit codes.

## Storage layout

```text
project/
├── drift.toml
└── .drift/
    ├── .gitignore
    ├── metadata.json
    └── snapshots/
        └── a81f23d4901649b1aa477f030a879e44.json
```

A snapshot ID is a UUID4 encoded as 32 lowercase hex characters without hyphens. The ID matches the filename stem. Use a UTC timestamp assigned immediately after collection and serialize it with the `Z` suffix. Sort history by parsed timestamp and then ID. Metadata holds a single nullable baseline ID. Snapshots are immutable. A comparison's live observations use the same normalized probe model in memory and do not receive a snapshot ID.

## Configuration v1

```toml
schema_version = 1

[collectors]
system = true
runtime = true
docker = true
environment = true
dependency = true
git = true

[environment]
files = [".env.example"]
active_allowlist = ["DATABASE_URL", "NODE_ENV"]

[docker]
compose_project = "example"
```

The example shows opt-in settings. Generated defaults enable all six collectors. They omit `active_allowlist` and `compose_project`, and use an empty `files` list.

| Setting | v1 type and default |
| --- | --- |
| `schema_version` | Required integer with value `1`. |
| `collectors.<id>` | Boolean for each known collector. Omitted entries default to `true`. |
| `environment.files` | Array of unique project-relative path strings. Defaults to `[]`. |
| `environment.active_allowlist` | Optional array of unique exact names. Omission captures all active names. An empty array selects zero active names. |
| `docker.compose_project` | Optional literal Compose name matching `^[a-z0-9][a-z0-9_-]*$`. Service collection is enabled only when set. |

Reject unknown settings, wrong types, and unsafe paths. Paths use slash-separated relative components. Reject empty, dot, parent, absolute, drive-qualified, device, and ambiguous components. Check duplicate paths using platform path case rules. Check allowlist names for duplicates after uppercasing on Windows. Names must be nonempty and free of NUL and `=`.

Configuration loading checks the syntax of environment file paths. Existence, file type, and the absence of symlinks or junctions are checked when the collector opens each file, so a missing configured file can be reported in its own result. Follow the [filesystem rules](SECURITY.md#filesystem-safety). Environment directory scanning, globs, shell commands, and interpolation are outside the configuration contract.

## Normalized observations

The probe ID is local to its collector. Status determines whether a value exists. Successful results contain typed values. Other statuses carry a stable reason code and no value.

| Collector | Probe IDs and successful value types |
| --- | --- |
| `system` | `os`, `os_version`, `architecture` are strings. |
| `runtime` | `python`, `node`, `npm`, `php`, `java`, `go` are normalized version strings. A missing executable is `unavailable` with `executable_missing`. An unsupported launcher or failed version probe has its own status. |
| `docker` | `installed`, `compose_installed`, and `daemon_reachable` are booleans. `client_version` and `compose_version` are strings. `services` maps each observed service name to a mapping of normalized container state to positive replica count. |
| `environment` | `active` and each `file:<relative-path>` contain sorted, unique name arrays. Each file has its own status. |
| `dependency` | Each `manifest:<relative-path>` contains the lowercase SHA-256 of its raw bytes. A missing standard file is `unavailable` with `not_found`. |
| `git` | `repository` is boolean. `branch` and `commit` are strings when present. `worktree` is `clean` or `dirty`. Detached HEAD and unborn commits use explicit `not_applicable` reasons. Git stays outside the environment comparison. |

The dependency collector checks these exact root-relative paths without recursion.

```text
pyproject.toml
uv.lock
requirements.txt
package.json
package-lock.json
pnpm-lock.yaml
yarn.lock
composer.json
composer.lock
go.mod
go.sum
```

Use an incremental SHA-256 hash and a 64 MiB per-file limit. A file that is too large, changes detectably during hashing, or cannot be safely read has a gap. Environment files are UTF-8 with a 1 MiB per-file limit. Accept blank lines, comments, and assignments with optional `export` and identifiers matching `^[A-Za-z_][A-Za-z0-9_]*$`. Allow horizontal whitespace around the assignment separator. An unquoted value ends at the line break. A value starting with a single or double quote ends at the matching quote and may span lines. Treat an escaped quote inside double quotes as part of the value. Skip the value and recognize only whitespace or a comment after a closing quote. Never evaluate expressions or retain value text. Unrecognized syntax, an unterminated quote, or a read error makes that file probe incomplete. A missing configured file is `unavailable` with `not_found` and counts as a coverage gap.

Active names use the calling process's name semantics. Preserve names on case-sensitive platforms and normalize to uppercase on Windows. Store the effective presentation case and allowlist in the snapshot's scope. Match the allowlist using the same normalization. File declarations preserve their spelling on all platforms. Invalid Unicode input produces a sanitized failed probe. Names and declarations have presence represented by membership in their respective arrays.

Docker service states are `created`, `running`, `paused`, `restarting`, `removing`, `exited`, and `dead`. Empty successful service output yields an empty map. A local socket or pipe confirmed absent or refusing a connection can establish daemon unreachability. A timeout, permission error, or unsupported endpoint cannot. Dependent probes are `not_applicable` when a confirmed prerequisite is missing, except service collection explicitly requested in configuration reports unavailable coverage while its daemon is unreachable.

| Probe status | Meaning |
| --- | --- |
| `ok` | A validated observation, including a boolean `false` or an empty set. |
| `unavailable` | The probe could not obtain a value because a tool, input, or prerequisite is absent. The reason determines whether absence is comparable. |
| `unsupported` | The platform, launcher, or configuration prevents safe observation. |
| `failed` | A probe was attempted or prevented by an error. Examples include timeouts, parse errors, and permission failures. |
| `not_applicable` | A known condition makes the probe irrelevant, such as an unconfigured service scope or a version check for confirmed-absent Docker. |

Disabled collectors have the collector status `disabled` and an empty probe map. For other collectors, aggregate applicable probes as follows. Any mix of complete observations and gaps is `partial`. If all applicable probes are gaps, use `failed` when any failed, otherwise `unsupported` when any is unsupported, otherwise `unavailable`. An absent primary tool or repository, or all runtime executables absent, yields `unavailable` when other applicable probes introduce no gaps. Remaining complete results are `ok`. Non-applicable probes are ignored in this rollup.

## JSON schema v1

The schema below defines the JSON wire shapes. Validate the selected definition at its use site. Apply the probe-specific types above and the following invariants at the model boundary as well. Reject duplicate object members, non-finite numbers, invalid UTF-8, unknown fields, ID and filename mismatches, invalid UTC timestamps, and inconsistent aggregate statuses, scopes, probe keys, and payloads. A snapshot message is always present as a nullable field. A non-null message is a literal string up to 256 characters with no control characters.

<details>
<summary>Full JSON Schema for snapshots, metadata, changes, and coverage gaps</summary>

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "oneOf": [
    {"$ref": "#/$defs/snapshot"},
    {"$ref": "#/$defs/metadata"},
    {"$ref": "#/$defs/change"},
    {"$ref": "#/$defs/gap"}
  ],
  "$defs": {
    "snapshot_id": {
      "type": "string",
      "pattern": "^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$"
    },
    "name_set": {
      "type": "array",
      "items": {"type": "string", "minLength": 1},
      "uniqueItems": true
    },
    "state_counts": {
      "type": "object",
      "minProperties": 1,
      "propertyNames": {
        "enum": ["created", "running", "paused", "restarting", "removing", "exited", "dead"]
      },
      "additionalProperties": {"type": "integer", "minimum": 1}
    },
    "collector_id": {
      "enum": ["system", "runtime", "docker", "environment", "dependency", "git"]
    },
    "comparison_collector_id": {
      "allOf": [{"$ref": "#/$defs/collector_id"}, {"not": {"const": "git"}}]
    },
    "collector_status": {
      "enum": ["ok", "partial", "unavailable", "unsupported", "failed", "disabled"]
    },
    "diagnostic_code": {
      "enum": [
        "executable_missing", "not_found", "permission_denied", "timeout", "output_limit",
        "size_limit", "unsafe_path", "unsupported_platform", "unsupported_launcher",
        "unsupported_checkout", "invalid_output", "invalid_input", "io_error", "command_failed",
        "collector_error", "input_changed", "daemon_unreachable", "prerequisite_missing",
        "not_configured", "detached_head", "unborn_head"
      ]
    },
    "probe": {
      "type": "object",
      "additionalProperties": false,
      "required": ["status"],
      "properties": {
        "status": {"enum": ["ok", "unavailable", "unsupported", "failed", "not_applicable"]},
        "code": {"$ref": "#/$defs/diagnostic_code"},
        "value": {
          "oneOf": [
            {"type": "boolean"},
            {"type": "string", "minLength": 1},
            {"$ref": "#/$defs/name_set"},
            {"type": "object", "additionalProperties": {"$ref": "#/$defs/state_counts"}}
          ]
        }
      },
      "if": {"properties": {"status": {"const": "ok"}}},
      "then": {"required": ["value"], "not": {"required": ["code"]}},
      "else": {"required": ["code"], "not": {"required": ["value"]}}
    },
    "collector": {
      "type": "object",
      "additionalProperties": false,
      "required": ["status", "probes"],
      "properties": {
        "status": {"$ref": "#/$defs/collector_status"},
        "probes": {"type": "object", "additionalProperties": {"$ref": "#/$defs/probe"}}
      },
      "if": {"properties": {"status": {"const": "disabled"}}},
      "then": {"properties": {"probes": {"maxProperties": 0}}},
      "else": {"properties": {"probes": {"minProperties": 1}}}
    },
    "scope": {
      "type": "object",
      "additionalProperties": false,
      "required": ["active_allowlist", "active_name_case", "compose_project"],
      "properties": {
        "active_allowlist": {"oneOf": [{"type": "null"}, {"$ref": "#/$defs/name_set"}]},
        "active_name_case": {"enum": ["preserve", "uppercase"]},
        "compose_project": {"type": ["string", "null"], "pattern": "^[a-z0-9][a-z0-9_-]*$"}
      }
    },
    "snapshot": {
      "type": "object",
      "additionalProperties": false,
      "required": ["schema_version", "id", "created_at", "message", "scope", "collectors"],
      "properties": {
        "schema_version": {"const": 1},
        "id": {"$ref": "#/$defs/snapshot_id"},
        "created_at": {"type": "string", "format": "date-time", "pattern": "Z$"},
        "message": {"type": ["string", "null"], "minLength": 1, "maxLength": 256},
        "scope": {"$ref": "#/$defs/scope"},
        "collectors": {
          "type": "object",
          "required": ["system", "runtime", "docker", "environment", "dependency", "git"],
          "propertyNames": {"$ref": "#/$defs/collector_id"},
          "additionalProperties": {"$ref": "#/$defs/collector"}
        }
      }
    },
    "metadata": {
      "type": "object",
      "additionalProperties": false,
      "required": ["schema_version", "baseline_id"],
      "properties": {
        "schema_version": {"const": 1},
        "baseline_id": {"oneOf": [{"type": "null"}, {"$ref": "#/$defs/snapshot_id"}]}
      }
    },
    "change_value": {
      "oneOf": [
        {"type": ["null", "boolean", "string"]},
        {"$ref": "#/$defs/state_counts"}
      ]
    },
    "change": {
      "type": "object",
      "additionalProperties": false,
      "required": ["collector", "probe", "subject", "kind", "before", "after"],
      "properties": {
        "collector": {"$ref": "#/$defs/comparison_collector_id"},
        "probe": {"type": "string", "minLength": 1},
        "subject": {"type": ["string", "null"]},
        "kind": {"enum": ["added", "removed", "modified"]},
        "before": {"$ref": "#/$defs/change_value"},
        "after": {"$ref": "#/$defs/change_value"}
      }
    },
    "gap": {
      "type": "object",
      "additionalProperties": false,
      "required": ["collector", "probe", "side", "code"],
      "properties": {
        "collector": {"$ref": "#/$defs/comparison_collector_id"},
        "probe": {"type": ["string", "null"]},
        "side": {"enum": ["reference", "current", "both"]},
        "code": {
          "anyOf": [
            {"$ref": "#/$defs/diagnostic_code"},
            {"const": "scope_changed"}
          ]
        }
      }
    }
  }
}
```

</details>

### Examples

Example snapshot with the system and runtime collectors enabled.

```json
{
  "schema_version": 1,
  "id": "a81f23d4901649b1aa477f030a879e44",
  "created_at": "2026-11-26T03:40:00Z",
  "message": "Working environment",
  "scope": {"active_allowlist": null, "active_name_case": "preserve", "compose_project": null},
  "collectors": {
    "system": {
      "status": "ok",
      "probes": {
        "os": {"status": "ok", "value": "Linux"},
        "os_version": {"status": "ok", "value": "6.12.0"},
        "architecture": {"status": "ok", "value": "x86_64"}
      }
    },
    "runtime": {
      "status": "partial",
      "probes": {
        "python": {"status": "ok", "value": "3.12.8"},
        "node": {"status": "ok", "value": "20.18.0"},
        "npm": {"status": "ok", "value": "10.8.2"},
        "php": {"status": "unavailable", "code": "executable_missing"},
        "java": {"status": "failed", "code": "timeout"},
        "go": {"status": "unavailable", "code": "executable_missing"}
      }
    },
    "docker": {"status": "disabled", "probes": {}},
    "environment": {"status": "disabled", "probes": {}},
    "dependency": {"status": "disabled", "probes": {}},
    "git": {"status": "disabled", "probes": {}}
  }
}
```

Example metadata with a baseline and a confirmed change record.

```json
{"schema_version": 1, "baseline_id": "a81f23d4901649b1aa477f030a879e44"}
```

```json
{
  "collector": "runtime",
  "probe": "node",
  "subject": null,
  "kind": "modified",
  "before": "20.18.0",
  "after": "22.12.0"
}
```

Use integer schema versions independent of software versions. Readers recognize v1 only and report an unsupported version without rewriting data. Add explicit readers or migrations when a future task requires another version. Serialize JSON consistently with UTF-8, stable key order, and a final newline. Sort name arrays and comparison lists before serialization. Store diagnostic codes without raw diagnostic text.

## Comparison rules

Compare the saved reference to the current environment. Evaluate each probe in its stored scope. Snapshot IDs, timestamps, messages, and Git records are context and have no effect on drift.

| Condition | Comparison behavior |
| --- | --- |
| Same scope, known observations on both sides | Compare normalized values. Missing runtimes and standard dependency files with their expected absence codes are known absences. Two known absences match. A known absence becoming present is an addition. The reverse is a removal. |
| Failed, unsupported, or otherwise unavailable observation | Report a gap. Configured Docker service monitoring reports unavailable service coverage independently of daemon reachability. |
| Probe irrelevant on both sides, or a confirmed prerequisite change explains why a dependent version or availability probe is irrelevant on one side | Skip the probe. |
| Collector disabled | Skip it if disabled on both sides. If disabled on one side, report a collector-level scope gap on that side with a null probe. |
| Active name allowlist, active name case, or Compose project changed | Report a scope gap for the affected probe with side `both`. Compare other probes where possible. |
| Path added to or removed from `environment.files` | Report a scope gap on the side without that file probe. |

Compare strings and booleans by normalized value, name sets by member, and container state counts by service. Emit one change record per changed scalar, name, or service. Scalars have a null subject. Set and service changes use the name or service as the subject. Use null for the absent side of an addition or removal and `true` for a present name. A boolean `false` represents a present observation.

Sort changes by collector, probe, and subject. Sort gaps by collector, probe, side, and code. Merge identical gap reasons on the same probe across both sides into one gap with side `both`. With zero comparable environment observations, the comparison is incomplete and includes the outcome-level `no_comparable_observations` warning outside the gap list.

## Storage and recovery

- Initial setup uses an atomic no-clobber write for each new managed file. Create the directories and initial state before publishing a new `drift.toml`. For an existing configuration, validate it before completing missing setup. Preserve existing valid files. If history exists and metadata is missing or invalid, report an error so a possibly lost baseline is surfaced. Preserve an existing regular ignore file. Projects with customized ignore rules are responsible for maintaining local state exclusions.
- Create `.drift/.gitignore` with `/*` and `!/.gitignore` on separate lines. Snapshot paths, metadata, and temporary files remain ignored by default.
- Stage a same-directory temporary file with restrictive permissions, serialize and validate the bytes, flush and sync it, then publish without clobbering using an atomic hard link for new files. Remove the staging name after publication. Retry the snapshot with a new UUID if its final name already exists. Concurrent initializers use the winner's validated files. Baseline changes use `os.replace` after target validation. Sync the containing directory where supported. Report real sync failures, and leave any already-published complete file in place. A local filesystem must support the required publication operations for writes.
- Readers consider only canonical snapshot filenames. Ignore unrecognized entries and abandoned staging files. Listing can return readable snapshots and identify each damaged entry by filename-derived ID and a sanitized reason. Automatic latest selection fails closed if a canonical entry cannot be validated, since it might be the latest. Explicit lookups resolve an exact ID or a unique matching filename prefix before validating the selected file. Unrelated corruption does not prevent an explicit lookup.
- A baseline update atomically publishes the complete metadata document. The last completed replacement wins during concurrent updates. A reader sees the old or new pointer. A missing or corrupt baseline target is an error. Recovery is manual so Drift cannot overwrite a damaged snapshot or silently choose a new baseline.
- On Windows, metadata reads and replacements briefly retry path changes and sharing conflicts associated with concurrent access. A persistent failure surfaces as an error, with the last successfully published metadata left intact.

See [security](SECURITY.md) for permissions and path handling, and the [acceptance matrix](DEVELOPMENT.md#acceptance-matrix) for interruption and concurrency scenarios.
