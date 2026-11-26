"""Collect active names and dotenv declarations without recording values."""

import os
import re
from typing import BinaryIO

from drift.collectors.base import CollectorContext, Observation, ProbeIssue, ProbeResult
from drift.collectors.file_probe import read_file
from drift.config import ProjectConfig

_FILE_LIMIT = 1024 * 1024
_ASSIGNMENT = re.compile(r"(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*")


def probe_ids(config: ProjectConfig) -> tuple[str, ...]:
    return ("active", *(f"file:{path}" for path in config.environment.files))


def _active(context: CollectorContext) -> ProbeResult:
    allowlist = context.config.environment.active_allowlist
    names = set(os.environ)
    if os.name == "nt":
        names = {name.upper() for name in names}
    if allowlist is not None:
        names.intersection_update(allowlist)
    try:
        for name in names:
            name.encode("utf-8")
    except UnicodeError:
        return ProbeIssue("failed", "invalid_input")
    return Observation(sorted(names))


def _closing_quote(line: str, quote: str, start: int) -> int:
    escaped = False
    for index in range(start, len(line)):
        character = line[index]
        if character == quote and not escaped:
            return index
        escaped = quote == '"' and character == "\\" and not escaped
    return -1


def _declarations(context: CollectorContext, stream: BinaryIO) -> ProbeResult:
    data = bytearray()
    while context.remaining():
        chunk = stream.read(min(65536, _FILE_LIMIT + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > _FILE_LIMIT:
            return ProbeIssue("failed", "size_limit")
    else:
        return ProbeIssue("failed", "timeout")

    try:
        text = data.decode("utf-8")
    except UnicodeError:
        return ProbeIssue("failed", "invalid_input")

    names: set[str] = set()
    quote = ""
    for line in text.split("\n"):
        if not context.remaining():
            return ProbeIssue("failed", "timeout")
        line = line.removesuffix("\r")
        start = 0
        if not quote:
            line = line.lstrip(" \t")
            if not line or line.startswith("#"):
                continue
            assignment = _ASSIGNMENT.match(line)
            if not assignment:
                return ProbeIssue("failed", "invalid_input")
            names.add(assignment[1])
            start = assignment.end()
            if line[start : start + 1] not in {"'", '"'}:
                continue
            quote = line[start]
            start += 1
        end = _closing_quote(line, quote, start)
        if end >= 0:
            trailing = line[end + 1 :].lstrip(" \t")
            if trailing and not trailing.startswith("#"):
                return ProbeIssue("failed", "invalid_input")
            quote = ""
    if quote:
        return ProbeIssue("failed", "invalid_input")
    return Observation(sorted(names))


def collect(context: CollectorContext) -> dict[str, ProbeResult]:
    results = {"active": _active(context)}
    for path in context.config.environment.files:
        results[f"file:{path}"] = read_file(
            context, path, lambda stream: _declarations(context, stream)
        )
    return results
