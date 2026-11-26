"""Report versions from fixed probes for supported runtimes."""

import os
import re

from drift.collectors.base import CollectorContext, Observation, ProbeIssue, ProbeResult
from drift.collectors.runner import CommandOutput, launcher_paths, run_probe

_COMMANDS = {
    "python": ("-I", "-S", "--version"),
    "node": ("--version",),
    "npm": ("--version",),
    "php": ("-n", "-v"),
    "java": ("-version",),
    "go": ("version",),
}
PROBE_IDS = tuple(_COMMANDS)
_VERSION = rb"([0-9]+(?:\.[0-9]+)+(?:[A-Za-z0-9_.+\-]*))"
_PATTERNS = {
    "python": re.compile(rb"Python " + _VERSION),
    "node": re.compile(rb"v" + _VERSION),
    "npm": re.compile(_VERSION),
    "php": re.compile(rb"PHP " + _VERSION + rb"(?: \(.*\))?"),
    "java": re.compile(rb'(?:openjdk|java) version "' + _VERSION + rb'"(?: .*)?'),
    "go": re.compile(rb"go version go" + _VERSION + rb" [a-z0-9]+/[a-z0-9]+"),
}


def _windows_npm(context: CollectorContext) -> CommandOutput | ProbeIssue:
    for directory in launcher_paths():
        if not any(
            (directory / f"npm{suffix}").is_file()
            for suffix in (".cmd", ".bat", ".ps1")
        ):
            continue
        try:
            installation = directory.resolve(strict=True)
            node = (installation / "node.exe").resolve(strict=True)
            script = (installation / "node_modules/npm/bin/npm-cli.js").resolve(
                strict=True
            )
            if (
                node.parent == installation
                and script.is_relative_to(installation)
                and script.is_file()
            ):
                return run_probe(
                    node,
                    (str(script), "--version"),
                    cwd=context.root,
                    deadline=context.deadline,
                )
        except (OSError, RuntimeError):
            break
        break
    return ProbeIssue("unsupported", "unsupported_launcher")


def _probe(name: str, args: tuple[str, ...], context: CollectorContext) -> ProbeResult:
    output = run_probe(
        name,
        args,
        cwd=context.root,
        deadline=context.deadline,
        profile="go" if name == "go" else "default",
    )
    if name == "python" and output == ProbeIssue("unavailable", "executable_missing"):
        output = run_probe("python3", args, cwd=context.root, deadline=context.deadline)
    if (
        name == "npm"
        and os.name == "nt"
        and output == ProbeIssue("unsupported", "unsupported_launcher")
    ):
        output = _windows_npm(context)
    if isinstance(output, ProbeIssue):
        return output
    for stream in (output.stdout, output.stderr):
        for line in stream.splitlines():
            if match := _PATTERNS[name].fullmatch(line.strip()):
                return Observation(match[1].decode("ascii"))
    return ProbeIssue("failed", "invalid_output")


def collect(context: CollectorContext) -> dict[str, ProbeResult]:
    return {name: _probe(name, args, context) for name, args in _COMMANDS.items()}
