"""Hash the supported root-level dependency files."""

import hashlib
import os
from typing import BinaryIO

from drift.collectors.base import CollectorContext, Observation, ProbeIssue, ProbeResult
from drift.collectors.file_probe import read_file
from drift.paths import open_project_file

_FILES = (
    "pyproject.toml",
    "uv.lock",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "composer.json",
    "composer.lock",
    "go.mod",
    "go.sum",
)
PROBE_IDS = tuple(f"manifest:{path}" for path in _FILES)
_FILE_LIMIT = 64 * 1024 * 1024


def _signature(stream: BinaryIO) -> tuple[int, int, int, int, int]:
    info = os.fstat(stream.fileno())
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _checksum(context: CollectorContext, path: str, stream: BinaryIO) -> ProbeResult:
    before = _signature(stream)
    if before[2] > _FILE_LIMIT:
        return ProbeIssue("failed", "size_limit")
    hashed = 0
    digest = hashlib.sha256()
    while context.remaining():
        chunk = stream.read(min(65536, _FILE_LIMIT + 1 - hashed))
        if not chunk:
            break
        hashed += len(chunk)
        if hashed > _FILE_LIMIT:
            return ProbeIssue("failed", "size_limit")
        digest.update(chunk)
    else:
        return ProbeIssue("failed", "timeout")

    if before != _signature(stream) or hashed != before[2]:
        return ProbeIssue("failed", "input_changed")
    try:
        with open_project_file(context.root, path) as current:
            if before != _signature(current):
                return ProbeIssue("failed", "input_changed")
    except FileNotFoundError:
        return ProbeIssue("failed", "input_changed")
    return Observation(digest.hexdigest())


def collect(context: CollectorContext) -> dict[str, ProbeResult]:
    results: dict[str, ProbeResult] = {}
    for path in _FILES:
        results[f"manifest:{path}"] = read_file(
            context, path, lambda stream: _checksum(context, path, stream)
        )
    return results
