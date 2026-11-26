"""Map project file read failures to collector diagnostics."""

from collections.abc import Callable
from typing import BinaryIO

from drift.collectors.base import CollectorContext, ProbeIssue, ProbeResult
from drift.exceptions import UnsafePathError
from drift.paths import open_project_file


def read_file(
    context: CollectorContext, path: str, read: Callable[[BinaryIO], ProbeResult]
) -> ProbeResult:
    if not context.remaining():
        return ProbeIssue("failed", "timeout")
    try:
        with open_project_file(context.root, path) as stream:
            return read(stream)
    except FileNotFoundError:
        return ProbeIssue("unavailable", "not_found")
    except PermissionError:
        return ProbeIssue("failed", "permission_denied")
    except UnsafePathError:
        return ProbeIssue("failed", "unsafe_path")
    except OSError:
        return ProbeIssue("failed", "io_error")
