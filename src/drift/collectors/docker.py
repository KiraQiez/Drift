"""Collect Docker versions and project services through local endpoints only."""

import json
import re
import socket
import sys
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from drift.collectors.base import CollectorContext, Observation, ProbeIssue, ProbeResult
from drift.collectors.runner import CommandOutput, run_probe

PROBE_IDS = (
    "installed",
    "client_version",
    "compose_installed",
    "compose_version",
    "daemon_reachable",
    "services",
)
_NOT_INSTALLED = ProbeIssue("not_applicable", "prerequisite_missing")
_MISSING_EXECUTABLE = ProbeIssue("unavailable", "executable_missing")
_OFFLINE = ProbeIssue("unavailable", "daemon_unreachable")
_COMMAND_FAILED = ProbeIssue("failed", "command_failed")
_INVALID_OUTPUT = ProbeIssue("failed", "invalid_output")
_SERVICE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_VERSION = rb"v?([0-9]+(?:\.[0-9]+)+(?:[-+][a-zA-Z0-9.+-]+)?)"
_CLIENT_VERSION = re.compile(
    rb"Docker version " + _VERSION + rb"(?:, build [a-zA-Z0-9._-]+)?"
)
_SHORT_VERSION = re.compile(_VERSION)
_COMPOSE_VERSION = re.compile(rb"(?:Docker Compose version )?" + _VERSION)
_STATES = {"created", "running", "paused", "restarting", "removing", "exited", "dead"}
_FORMAT = '{{json (.Label "com.docker.compose.service")}}\t{{json .State}}'


def _version(
    output: CommandOutput | ProbeIssue, pattern: re.Pattern[bytes]
) -> ProbeResult:
    if isinstance(output, ProbeIssue):
        return output
    match = pattern.fullmatch(output.stdout.strip())
    return Observation(match[1].decode("ascii")) if match else _INVALID_OUTPUT


def _compose_exit(stderr: bytes) -> ProbeIssue:
    missing = (
        b"docker: unknown command: docker compose",
        b"docker: 'compose' is not a docker command.",
    )
    return (
        _MISSING_EXECUTABLE if stderr.strip().startswith(missing) else _COMMAND_FAILED
    )


def _daemon_exit(stderr: bytes) -> ProbeIssue:
    lines = stderr.lower().splitlines()
    for line in lines:
        if b"dial unix " in line:
            if (
                b"connect: no such file or directory" in line
                or b"connect: connection refused" in line
            ):
                return _OFFLINE
            if b"connect: permission denied" in line:
                return ProbeIssue("failed", "permission_denied")
        if b"/pipe/docker_engine" not in line:
            continue
        if (
            b"the system cannot find the file specified" in line
            or b"connection refused" in line
        ):
            return _OFFLINE
        if b"access is denied" in line:
            return ProbeIssue("failed", "permission_denied")
    return _COMMAND_FAILED


def _endpoint() -> str | ProbeIssue:
    if sys.platform == "win32":
        return "npipe:////./pipe/docker_engine"
    if sys.platform == "darwin":
        desktop = Path.home() / ".docker/run/docker.sock"
        if desktop.exists():
            return f"unix://{desktop}"
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        return "unix:///var/run/docker.sock"
    return ProbeIssue("unsupported", "unsupported_platform")


def _socket_issue(host: str, context: CollectorContext) -> ProbeIssue | None:
    if not host.startswith("unix://"):
        return None
    remaining = context.remaining()
    if not remaining:
        return ProbeIssue("failed", "timeout")
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(min(2, remaining))
            client.connect(host.removeprefix("unix://"))
    except (FileNotFoundError, ConnectionRefusedError):
        return _OFFLINE
    except PermissionError:
        return ProbeIssue("failed", "permission_denied")
    except TimeoutError:
        return ProbeIssue("failed", "timeout")
    except OSError:
        return ProbeIssue("failed", "io_error")
    return None


def _services(output: CommandOutput | ProbeIssue) -> ProbeResult:
    if isinstance(output, ProbeIssue):
        return output
    counts: dict[str, dict[str, int]] = {}
    try:
        for row in output.stdout.splitlines():
            raw_service, raw_state = row.split(b"\t")
            service, state = json.loads(raw_service), json.loads(raw_state)
            if not isinstance(service, str) or not _SERVICE.fullmatch(service):
                return _INVALID_OUTPUT
            if not isinstance(state, str) or state not in _STATES:
                return _INVALID_OUTPUT
            states = counts.setdefault(service, {})
            states[state] = states.get(state, 0) + 1
    except (ValueError, RecursionError):
        return _INVALID_OUTPUT
    return Observation(
        {name: dict(sorted(counts[name].items())) for name in sorted(counts)}
    )


def _user_compose(
    context: CollectorContext, isolated: Path
) -> CommandOutput | ProbeIssue:
    name = "docker-compose.exe" if sys.platform == "win32" else "docker-compose"
    try:
        plugin = (Path.home() / ".docker/cli-plugins" / name).resolve(strict=True)
        if plugin.is_relative_to(context.root.resolve()) or not plugin.is_file():
            return ProbeIssue("unsupported", "unsupported_launcher")
    except FileNotFoundError:
        return _MISSING_EXECUTABLE
    except (OSError, RuntimeError):
        return ProbeIssue("failed", "io_error")
    return run_probe(
        plugin,
        ("version", "--short"),
        cwd=context.root,
        deadline=context.deadline,
        docker_config=isolated,
    )


def collect(context: CollectorContext) -> dict[str, ProbeResult]:
    isolated = context.root / f".drift-docker-{uuid4().hex}"
    try:
        isolated.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        return dict.fromkeys(PROBE_IDS, ProbeIssue("failed", "io_error"))
    else:
        return dict.fromkeys(PROBE_IDS, ProbeIssue("failed", "unsafe_path"))

    def docker(
        *args: str, classify: Callable[[bytes], ProbeIssue] | None = None
    ) -> CommandOutput | ProbeIssue:
        return run_probe(
            "docker",
            ("--config", str(isolated), *args),
            cwd=context.root,
            deadline=context.deadline,
            docker_config=isolated,
            classify_exit=classify,
        )

    project = context.config.docker.compose_project
    results: dict[str, ProbeResult] = {
        "services": ProbeIssue("not_applicable", "not_configured")
        if project is None
        else _NOT_INSTALLED
    }
    client = docker("--version")
    if isinstance(client, ProbeIssue) and client != _COMMAND_FAILED:
        results.update(dict.fromkeys(PROBE_IDS[:-1], client))
        if client == _MISSING_EXECUTABLE:
            results.update(dict.fromkeys(PROBE_IDS[:-1], _NOT_INSTALLED))
            results["installed"] = Observation(False)
        if project is not None:
            results["services"] = results["daemon_reachable"]
        return results
    results["installed"] = Observation(True)
    results["client_version"] = _version(client, _CLIENT_VERSION)

    compose = docker("compose", "version", classify=_compose_exit)
    if compose == _MISSING_EXECUTABLE:
        compose = _user_compose(context, isolated)
    if isinstance(compose, ProbeIssue):
        results["compose_installed"] = (
            Observation(False) if compose == _MISSING_EXECUTABLE else compose
        )
        results["compose_version"] = (
            _NOT_INSTALLED if compose == _MISSING_EXECUTABLE else compose
        )
    else:
        results["compose_installed"] = Observation(True)
        results["compose_version"] = _version(compose, _COMPOSE_VERSION)

    host = _endpoint()
    if isinstance(host, ProbeIssue):
        issue: ProbeIssue | None = host
    else:
        issue = _socket_issue(host, context)
        if issue is None:
            version = _version(
                docker(
                    "--host",
                    host,
                    "version",
                    "--format",
                    "{{.Server.Version}}",
                    classify=_daemon_exit,
                ),
                _SHORT_VERSION,
            )
            if isinstance(version, ProbeIssue):
                issue = version
    if issue is not None:
        results["daemon_reachable"] = Observation(False) if issue == _OFFLINE else issue
        if project is not None:
            results["services"] = issue
        return results

    assert isinstance(host, str)
    results["daemon_reachable"] = Observation(True)
    if project is not None:
        results["services"] = _services(
            docker(
                "--host",
                host,
                "container",
                "ls",
                "--all",
                "--filter",
                f"label=com.docker.compose.project={project}",
                "--format",
                _FORMAT,
            )
        )
    return results
