# Security and privacy

Drift is a local diagnostic tool. It writes its own project configuration and state. Collectors observe the machine and project without installing software, modifying source or environment configuration, or starting and stopping services. The CLI has no telemetry, upload, cloud storage, or remote Docker control path.

## Threat model

| Threat | Mitigation and limit |
| --- | --- |
| Credentials in the process or environment files | Read active keys only. Scan declared names without evaluating values, expanding variables, or exporting anything. Never store values or hashes of values. Keep parser failures free of input excerpts. |
| Secrets in command output | Run fixed probes, parse only narrowly defined fields, and discard raw stdout and stderr. Keep exception rendering, subprocess traces, and Pydantic input excerpts out of user-facing diagnostics. |
| Overbroad project access | Validate project-relative paths before access. Reject symlinks, junctions, traversal, and non-regular files. Docker uses explicit local endpoints and an explicit Compose project label for service status. |
| Command execution through repository data | Use fixed executable names and argument arrays. Disable Git behaviors that can execute hooks, filters, or fetch data, or skip working-tree inspection when safety cannot be established. |
| Local disclosure | Treat names, file paths, service names, Git metadata, hashes, and notes as sensitive. Use restrictive permissions where supported and exclude local state from Git by default. |
| Malformed or changed state | Validate types, schema versions, filenames, and paths on every read. Report corruption without echoing file contents. Publish completed files atomically. |
| Terminal injection | Escape control characters and disable Rich markup interpretation for all collected and user-supplied text. Serialize JSON as data through the standard encoder. |

## Subprocess safety

Resolve executables from the calling user's trusted installation and absolute PATH entries. Ignore implicit current-directory search and relative PATH entries. Pass an absolute executable path, an argument array, and a controlled working directory. Use no shell, a closed stdin, an explicit environment allowlist, and the [execution bounds](ARCHITECTURE.md#execution-limits). Keep only launch essentials and each probe's required controls in the child environment. Do not forward tool startup overrides, credential variables, remote endpoints, or general project environment contents.

The shared runner retains successful stdout and stderr only for parsing. A failed command returns a stable reason code without either stream. On POSIX, cleanup after timeout or overflow also kills descendants that remain in the probe's process group. On Windows, cleanup targets the launched process.

The runtime collector uses fixed version probes and suppresses optional startup customization where supported. On Windows, launch native executables directly. A recognized npm installation may use a directly launched Node executable with its verified, fixed npm CLI script. An unsupported batch or shell launcher yields an unsupported status. Go uses the locally selected binary with automatic toolchain download disabled. Some probes therefore report the installed version when a runtime relies on startup customization.

For Docker, bypass remote contexts with a fixed local host argument on daemon commands. Start with Docker's standard Unix socket on Linux and macOS and its default named pipe on Windows. On macOS, prefer the local Docker Desktop socket under the user's Docker directory when it exists. Confirm reachability with the server version field and retain only the reachability result. Observe services with `docker container ls --all` filtered by the exact `com.docker.compose.project` label, and request only `com.docker.compose.service` and state. Do not load Compose project configuration, inspect containers, request environment data, or fall back to unfiltered or remote queries. Compose version probing uses only the version command. [Docker host options](https://docs.docker.com/reference/cli/docker/#specify-daemon-host--h---host) · [Docker container listing](https://docs.docker.com/reference/cli/docker/container/ls/)

Docker uses a checked, uncreated configuration path under the project root. Compose detection tries Docker's system plugin locations and then the standard per-user executable. User plugins must resolve outside the project tree. Only fixed exit diagnostics are classified, and raw output is discarded.

For Git, examine a standard root-local checkout. Disable optional locks, pagers, fsmonitor, and submodule scanning. Use a controlled Git environment without user, system, or injected Git configuration. Check the local configuration without following includes before running a working-tree probe. Skip the probe if includes, external filters, partial clone settings, external metadata, or another setting could initiate commands or network fetches. Keep branch and commit only if their read-only probes can be run under the same trust checks. Discard paths in status output and retain only the normalized worktree status. Repository layouts that cannot meet these guarantees get an explicit unsupported or partial status. [Git status](https://git-scm.com/docs/git-status) · [Git attributes](https://git-scm.com/docs/gitattributes)

The Git preflight checks metadata for links and alternate stores, then compares local config key names against an allowlist. Checkouts with unrecognized settings or separate Git directories can report `unsupported_checkout`. The status probe disables all Git transport protocols as well as lazy fetching.

## Filesystem safety

Resolve the user-selected project root once. Confine managed state and configured input paths to it. Check every descendant path component, verify the target type, and use descriptor-relative operations with no-follow flags where the platform supports them. Use validated filenames generated by Drift for storage. Reject unsafe or ambiguous components, including Windows drive or device paths. Do not open FIFOs, devices, or sockets as files to parse or hash.

The shared reader checks directory and file types without following links. When descriptor-relative reads are unavailable, it checks each component and compares the opened file's identity with path metadata before allowing reads. These checks reduce substitution risk within the [documented platform limits](#limits-and-security-tests).

Create private state directories and files with owner-only access on POSIX, using `0700` and `0600` before data is visible. On Windows, rely on the user's inherited directory ACLs. The application cannot guarantee private access if project permissions are shared. Do not trust the ignore rules to hide already tracked or force-added files. See [data model](DATA_MODEL.md#storage-and-recovery) for publication and recovery.

## Limits and security tests

Drift assumes the invoking user controls the machine, the project filesystem, and the selected tool binaries. It is not a sandbox for untrusted executables or a defense against another process with the same account's permissions. File and directory checks reduce path substitution risks. Platform APIs and filesystem semantics constrain how fully Drift can prevent concurrent path replacement and guarantee durability.

Snapshot messages come from the caller. They are rendered as literal text and validated for size and control characters, but Drift cannot reliably recognize arbitrary secrets in free text, names, or branch labels. Keep secrets out of messages and review JSON or terminal output before sharing it. An unrecognized or malformed observed field produces a structured status without displaying raw input.

Exercise sentinel secrets in subprocess streams, environment values, configured files, and validation errors. Test flag injection, unsafe launchers, unexpected Docker endpoints, Git filters and fsmonitor hooks, traversal, links and junctions, special files, permissions, and terminal escape sequences. See the [acceptance matrix](DEVELOPMENT.md#acceptance-matrix).
