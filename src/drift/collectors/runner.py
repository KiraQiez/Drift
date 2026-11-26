"""Run fixed, local probe commands with bounded output and duration."""

import os
import re
import signal
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic, sleep

from drift.collectors.base import ProbeIssue

_COMMAND_TIMEOUT = 2.0
_OUTPUT_LIMIT = 256 * 1024
_POLL_INTERVAL = 0.01
_LAUNCHER_NAME = re.compile(r"[a-zA-Z0-9_+.\-]+")
_WINDOWS_WRAPPERS = (".cmd", ".bat", ".ps1")


@dataclass(frozen=True)
class CommandOutput:
    """Transient output for a collector parser. Keep it out of reports."""

    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)


def _resolve(executable: str, search: Sequence[Path]) -> Path | ProbeIssue:
    if executable in {".", ".."} or not _LAUNCHER_NAME.fullmatch(executable):
        return ProbeIssue("failed", "invalid_input")

    windows = os.name == "nt"
    suffix = Path(executable).suffix.lower()
    if windows and suffix not in {".exe", *_WINDOWS_WRAPPERS}:
        names = tuple(
            executable + extension for extension in (".exe", *_WINDOWS_WRAPPERS)
        )
    else:
        names = (executable,)

    for directory in search:
        for name in names:
            path = directory / name
            if path.is_file() and os.access(path, os.X_OK):
                if windows and path.suffix.lower() != ".exe":
                    return ProbeIssue("unsupported", "unsupported_launcher")
                return path
    return ProbeIssue("unavailable", "executable_missing")


def _capture(
    process: subprocess.Popen[bytes], deadline: float
) -> CommandOutput | ProbeIssue:
    assert process.stdout is not None and process.stderr is not None
    stdout, stderr = bytearray(), bytearray()
    streams = {process.stdout.fileno(): stdout, process.stderr.fileno(): stderr}
    for fd in streams:
        os.set_blocking(fd, False)

    remaining = _OUTPUT_LIMIT
    while monotonic() < deadline:
        received = False
        for fd, output in tuple(streams.items()):
            try:
                chunk = os.read(fd, min(8192, remaining + 1))
            except BlockingIOError:
                continue
            if not chunk:
                del streams[fd]
                continue
            if len(chunk) > remaining:
                return ProbeIssue("failed", "output_limit")
            output.extend(chunk)
            remaining -= len(chunk)
            received = True

        if not streams and (returncode := process.poll()) is not None:
            if returncode != 0:
                return ProbeIssue("failed", "command_failed")
            return CommandOutput(bytes(stdout), bytes(stderr))
        if not received:
            sleep(min(_POLL_INTERVAL, max(0, deadline - monotonic())))
    return ProbeIssue("failed", "timeout")


def _stop(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            process.kill()
    except ProcessLookupError:
        pass
    process.wait()


def run_probe(
    executable: str, args: Sequence[str], *, cwd: Path, deadline: float
) -> CommandOutput | ProbeIssue:
    """Run a trusted tool name with arguments supplied by collector code."""
    if not cwd.is_absolute():
        return ProbeIssue("failed", "invalid_input")
    deadline = min(deadline, monotonic() + _COMMAND_TIMEOUT)
    if monotonic() >= deadline:
        return ProbeIssue("failed", "timeout")

    search = [
        path
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if (path := Path(entry)).is_absolute()
    ]
    environment = (
        {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
        if os.name == "nt"
        else {}
    )
    environment.update(PATH=os.pathsep.join(map(str, search)), LC_ALL="C", LANG="C")

    try:
        if not cwd.is_dir():
            return ProbeIssue("failed", "invalid_input")
        launcher = _resolve(executable, search)
        if isinstance(launcher, ProbeIssue):
            return launcher
        if monotonic() >= deadline:
            return ProbeIssue("failed", "timeout")
        with subprocess.Popen(
            [str(launcher), *args],
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=os.name == "posix",
        ) as process:
            finished = False
            try:
                result = _capture(process, deadline)
                finished = (
                    isinstance(result, CommandOutput) or result.code == "command_failed"
                )
                return result
            finally:
                if not finished:
                    _stop(process)
    except FileNotFoundError:
        return ProbeIssue("unavailable", "executable_missing")
    except PermissionError:
        return ProbeIssue("failed", "permission_denied")
    except OSError:
        return ProbeIssue("failed", "io_error")
    except ValueError:
        return ProbeIssue("failed", "invalid_input")
