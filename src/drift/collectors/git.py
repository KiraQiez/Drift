"""Read Git context from a standard local checkout after a safety preflight."""

import os
import re
import stat
from pathlib import Path

from drift.collectors.base import CollectorContext, Observation, ProbeIssue, ProbeResult
from drift.collectors.runner import CommandOutput, run_probe

PROBE_IDS = ("repository", "branch", "commit", "worktree")
_UNSAFE = ProbeIssue("unsupported", "unsupported_checkout")
_INVALID = ProbeIssue("failed", "invalid_output")
_OBJECT_ID = re.compile(rb"(?:[a-f0-9]{40}|[a-f0-9]{64})")
_CORE_KEYS = {
    b"core.repositoryformatversion",
    b"core.filemode",
    b"core.bare",
    b"core.logallrefupdates",
    b"core.ignorecase",
    b"core.precomposeunicode",
    b"core.symlinks",
    b"core.autocrlf",
    b"core.eol",
    b"core.safecrlf",
    b"core.checkstat",
    b"core.trustctime",
    b"core.longpaths",
    b"extensions.objectformat",
    b"user.name",
    b"user.email",
}
_SECTION_KEYS = {
    b"branch": {b"remote", b"merge", b"vscode-merge-base"},
    b"remote": {b"url", b"fetch", b"pushurl", b"push"},
}
_EXTERNAL_METADATA = {
    "commondir",
    "gitdir",
    "config.worktree",
    "objects/info/alternates",
    "objects/info/http-alternates",
}


def _linked(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _raise_walk_error(error: OSError) -> None:
    raise error


def _preflight_metadata(metadata: Path, context: CollectorContext) -> ProbeIssue | None:
    for expected in ("HEAD", "config", "objects"):
        try:
            info = (metadata / expected).lstat()
        except FileNotFoundError:
            return _UNSAFE
        expected_type = stat.S_ISDIR if expected == "objects" else stat.S_ISREG
        if _linked(info) or not expected_type(info.st_mode):
            return _UNSAFE

    for directory, subdirectories, files in os.walk(
        metadata, followlinks=False, onerror=_raise_walk_error
    ):
        for name in (*subdirectories, *files):
            if not context.remaining():
                return ProbeIssue("failed", "timeout")
            path = Path(directory) / name
            relative = path.relative_to(metadata).as_posix()
            if relative in _EXTERNAL_METADATA or relative.endswith(".promisor"):
                return _UNSAFE
            info = path.lstat()
            if _linked(info) or not (
                stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)
            ):
                return _UNSAFE
    return None


def _allowed_key(key: bytes) -> bool:
    if key in _CORE_KEYS:
        return True
    parts = key.split(b".")
    return len(parts) >= 3 and parts[-1] in _SECTION_KEYS.get(parts[0], set())


def _preflight_config(metadata: Path, context: CollectorContext) -> ProbeIssue | None:
    def config(*args: str) -> CommandOutput | ProbeIssue:
        return run_probe(
            "git",
            (
                "--no-pager",
                f"--git-dir={os.devnull}",
                "config",
                "--file",
                str(metadata / "config"),
                "--no-includes",
                *args,
            ),
            cwd=context.root,
            deadline=context.deadline,
            profile="git",
        )

    output = config("--null", "--name-only", "--list")
    if isinstance(output, ProbeIssue):
        return output
    if output.stdout and not output.stdout.endswith(b"\0"):
        return _INVALID
    keys = output.stdout.split(b"\0")[:-1]
    if not all(map(_allowed_key, keys)):
        return _UNSAFE
    if b"core.bare" in keys:
        bare = config("--type=bool", "--get-all", "core.bare")
        if isinstance(bare, ProbeIssue):
            return bare
        values = bare.stdout.splitlines()
        if not values or any(value != b"false" for value in values):
            return _UNSAFE
    return None


def _status(output: bytes) -> dict[str, ProbeResult]:
    oid = head = b""
    dirty = False
    if not output.endswith(b"\0"):
        return dict.fromkeys(PROBE_IDS[1:], _INVALID)
    for record in output.split(b"\0")[:-1]:
        if record.startswith(b"# branch.oid "):
            oid = record.removeprefix(b"# branch.oid ")
        elif record.startswith(b"# branch.head "):
            head = record.removeprefix(b"# branch.head ")
        elif record.startswith((b"1 ", b"u ", b"? ")):
            dirty = True
        elif not record.startswith(b"# "):
            return dict.fromkeys(PROBE_IDS[1:], _INVALID)

    branch: ProbeResult = _INVALID
    if head == b"(detached)":
        branch = ProbeIssue("not_applicable", "detached_head")
    elif head and all(byte >= 32 and byte != 127 for byte in head):
        try:
            branch = Observation(head.decode("utf-8"))
        except UnicodeError:
            pass
    commit: ProbeResult = _INVALID
    if oid == b"(initial)":
        commit = ProbeIssue("not_applicable", "unborn_head")
    elif _OBJECT_ID.fullmatch(oid):
        commit = Observation(oid.decode("ascii"))
    if not oid or not head:
        return dict.fromkeys(PROBE_IDS[1:], _INVALID)
    return {
        "branch": branch,
        "commit": commit,
        "worktree": Observation("dirty" if dirty else "clean"),
    }


def collect(context: CollectorContext) -> dict[str, ProbeResult]:
    metadata = context.root / ".git"
    try:
        info = metadata.lstat()
    except FileNotFoundError:
        return {
            "repository": Observation(False),
            **dict.fromkeys(
                PROBE_IDS[1:], ProbeIssue("not_applicable", "prerequisite_missing")
            ),
        }
    except PermissionError:
        return dict.fromkeys(PROBE_IDS, ProbeIssue("failed", "permission_denied"))
    except OSError:
        return dict.fromkeys(PROBE_IDS, ProbeIssue("failed", "io_error"))
    if _linked(info) or not stat.S_ISDIR(info.st_mode):
        return dict.fromkeys(PROBE_IDS, _UNSAFE)

    try:
        issue = _preflight_metadata(metadata, context) or _preflight_config(
            metadata, context
        )
    except PermissionError:
        issue = ProbeIssue("failed", "permission_denied")
    except OSError:
        issue = ProbeIssue("failed", "io_error")
    if issue is not None:
        return {"repository": Observation(True), **dict.fromkeys(PROBE_IDS[1:], issue)}

    output = run_probe(
        "git",
        (
            "--no-pager",
            "--no-optional-locks",
            f"--git-dir={metadata}",
            f"--work-tree={context.root}",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            f"core.attributesFile={os.devnull}",
            "-c",
            f"core.excludesFile={os.devnull}",
            "status",
            "--porcelain=v2",
            "--branch",
            "-z",
            "--untracked-files=normal",
            "--ignore-submodules=all",
            "--no-renames",
            "--no-ahead-behind",
        ),
        cwd=context.root,
        deadline=context.deadline,
        profile="git",
    )
    if isinstance(output, ProbeIssue):
        return {"repository": Observation(True), **dict.fromkeys(PROBE_IDS[1:], output)}
    return {"repository": Observation(True), **_status(output.stdout)}
