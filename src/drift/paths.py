"""Read regular files beneath a resolved project root."""

import errno
import os
import re
import stat
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import BinaryIO

from drift.exceptions import UnsafePathError

_INVALID_CHARACTER = re.compile(r'[<>:"\\|?*\x00-\x1f\x7f\ud800-\udfff]')
_RESERVED_NAME = re.compile(r"(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[0-9¹²³])")
_DESCRIPTOR_READS = (
    os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
)


def project_path_parts(relative_path: str) -> tuple[str, ...]:
    """Validate portable relative syntax before a path can be normalized."""
    parts = tuple(relative_path.split("/"))
    for part in parts:
        stem = part.partition(".")[0].rstrip(" ").upper()
        if (
            not part
            or part.endswith((" ", "."))
            or _INVALID_CHARACTER.search(part)
            or _RESERVED_NAME.fullmatch(stem)
        ):
            raise UnsafePathError("Use a safe, slash-separated project-relative path.")
    return parts


def _require_kind(info: os.stat_result, *, directory: bool) -> None:
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    reparse_point = (
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )
    if reparse_point or not kind(info.st_mode):
        raise UnsafePathError(
            "Project paths must use real directories and regular files."
        )


@contextmanager
def _open_relative(root: Path, parts: tuple[str, ...]) -> Iterator[BinaryIO]:
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        with ExitStack() as directories:
            directory_fd = os.open(root, directory_flags)
            directories.callback(os.close, directory_fd)
            for part in parts[:-1]:
                directory_fd = os.open(part, directory_flags, dir_fd=directory_fd)
                directories.callback(os.close, directory_fd)

            name = parts[-1]
            _require_kind(
                os.stat(name, dir_fd=directory_fd, follow_symlinks=False),
                directory=False,
            )
            descriptor = os.open(
                name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory_fd,
            )
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise UnsafePathError(
                "Project paths must use real directories and regular files."
            ) from None
        raise

    with os.fdopen(descriptor, "rb") as stream:
        _require_kind(os.fstat(stream.fileno()), directory=False)
        yield stream


def _checked_file(root: Path, parts: tuple[str, ...]) -> tuple[Path, os.stat_result]:
    _require_kind(root.lstat(), directory=True)
    path = root
    for part in parts[:-1]:
        path = path / part
        _require_kind(path.lstat(), directory=True)
    path = path / parts[-1]
    info = path.lstat()
    _require_kind(info, directory=False)
    return path, info


@contextmanager
def open_project_file(root: Path, relative_path: str) -> Iterator[BinaryIO]:
    """Open a read-only binary stream, rejecting links and special files."""
    parts = project_path_parts(relative_path)
    if _DESCRIPTOR_READS:
        with _open_relative(root, parts) as stream:
            yield stream
        return

    path, before = _checked_file(root, parts)
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        _require_kind(opened, directory=False)
        _, after = _checked_file(root, parts)
        if not (os.path.samestat(before, opened) and os.path.samestat(opened, after)):
            raise UnsafePathError("The project file changed while it was being opened.")
        yield stream
