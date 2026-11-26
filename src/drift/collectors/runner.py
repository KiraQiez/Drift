"""Run fixed, local probe commands with bounded output and duration."""

import os
import re
import signal
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic, sleep
from typing import Literal

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


def launcher_paths() -> list[Path]:
    """Return absolute entries in the invoking user's PATH."""
    return [
        path
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if (path := Path(entry)).is_absolute()
    ]


def _resolve(executable: str | Path, search: Sequence[Path]) -> Path | ProbeIssue:
    if isinstance(executable, Path):
        if not executable.is_absolute():
            return ProbeIssue("failed", "invalid_input")
        return _resolve(executable.name, (executable.parent,))
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
    process: subprocess.Popen[bytes],
    deadline: float,
    classify_exit: Callable[[bytes], ProbeIssue] | None,
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
                if classify_exit is not None:
                    return classify_exit(bytes(stderr))
                return ProbeIssue("failed", "command_failed")
            return CommandOutput(bytes(stdout), bytes(stderr))
        if not received:
            sleep(min(_POLL_INTERVAL, max(0, deadline - monotonic())))
    return ProbeIssue("failed", "timeout")


def _stop(process: subprocess.Popen[bytes]) -> None:
    try:
        if sys.platform != "win32" and os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            process.kill()
    except ProcessLookupError:
        pass
    process.wait()


def run_probe(
    executable: str | Path,
    args: Sequence[str],
    *,
    cwd: Path,
    deadline: float,
    profile: Literal["default", "go", "git"] = "default",
    docker_config: Path | None = None,
    classify_exit: Callable[[bytes], ProbeIssue] | None = None,
) -> CommandOutput | ProbeIssue:
    """Run a trusted tool name with arguments supplied by collector code."""
    if not cwd.is_absolute():
        return ProbeIssue("failed", "invalid_input")
    deadline = min(deadline, monotonic() + _COMMAND_TIMEOUT)
    if monotonic() >= deadline:
        return ProbeIssue("failed", "timeout")

    search = launcher_paths()
    environment = (
        {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
        if os.name == "nt"
        else {}
    )
    environment.update(PATH=os.pathsep.join(map(str, search)), LC_ALL="C", LANG="C")
    if profile == "go":
        environment.update(GOTOOLCHAIN="local", GOENV="off")
    elif profile == "git":
        environment.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_ATTR_NOSYSTEM="1",
            GIT_ALLOW_PROTOCOL="",
            GIT_NO_LAZY_FETCH="1",
            GIT_NO_REPLACE_OBJECTS="1",
            GIT_TERMINAL_PROMPT="0",
            GIT_OPTIONAL_LOCKS="0",
        )
    if docker_config is not None:
        environment["DOCKER_CONFIG"] = str(docker_config)

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
                result = _capture(process, deadline, classify_exit)
                finished = process.returncode is not None
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
