"""Read and atomically publish project-local v1 records."""

import errno
import json
import os
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from drift.exceptions import (
    AmbiguousSnapshotError,
    InvalidSnapshotError,
    SnapshotNotFoundError,
    StorageError,
    UnsafePathError,
    UnsupportedSchemaError,
)
from drift.models import (
    Metadata,
    Snapshot,
    StrictRecord,
    is_snapshot_id,
    is_snapshot_reference,
)
from drift.paths import (
    open_project_file,
    project_directory,
    project_path_parts,
    require_kind,
)

STATE = ".drift"
SNAPSHOTS = (STATE, "snapshots")
METADATA = f"{STATE}/metadata.json"


def _sync_directory(descriptor: int | None) -> None:
    if descriptor is not None:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if error.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
                raise


def ensure_directory(root: Path, relative: str) -> bool:
    """Create one private directory or validate the existing directory."""
    *parents, name = project_path_parts(relative)
    try:
        with project_directory(root, tuple(parents)) as (directory, descriptor):
            entry = str(directory / name) if descriptor is None else name
            try:
                os.mkdir(entry, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                require_kind(
                    os.stat(entry, dir_fd=descriptor, follow_symlinks=False),
                    directory=True,
                )
                return False
            _sync_directory(descriptor)
            return True
    except OSError:
        raise StorageError("Could not prepare Drift's local directories.") from None


def publish_file(
    root: Path, relative: str, data: bytes, *, replace: bool = False
) -> bool:
    """Publish complete bytes, returning false if a no-clobber target exists."""
    *parents, name = project_path_parts(relative)
    try:
        with project_directory(root, tuple(parents)) as (directory, descriptor):
            target = str(directory / name) if descriptor is None else name
            try:
                info = os.stat(target, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                if replace:
                    raise
            else:
                require_kind(info, directory=False)
                if not replace:
                    return False

            stage_name = f".drift-stage-{uuid4().hex}"
            stage = str(directory / stage_name) if descriptor is None else stage_name
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            staged_fd = os.open(stage, flags, mode=0o600, dir_fd=descriptor)
            try:
                with os.fdopen(staged_fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                if replace:
                    os.replace(
                        stage, target, src_dir_fd=descriptor, dst_dir_fd=descriptor
                    )
                else:
                    try:
                        os.link(
                            stage,
                            target,
                            src_dir_fd=descriptor,
                            dst_dir_fd=descriptor,
                            follow_symlinks=False,
                        )
                    except FileExistsError:
                        require_kind(
                            os.stat(target, dir_fd=descriptor, follow_symlinks=False),
                            directory=False,
                        )
                        return False
            finally:
                try:
                    os.unlink(stage, dir_fd=descriptor)
                except FileNotFoundError:
                    pass
            _sync_directory(descriptor)
            return True
    except (OSError, NotImplementedError):
        raise StorageError("Could not publish Drift project state safely.") from None


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    raise ValueError("Non-finite JSON number.")


def _read_record[Record: StrictRecord](
    root: Path,
    relative: str,
    record: type[Record],
    damaged: type[StorageError] | type[InvalidSnapshotError],
) -> Record:
    try:
        with open_project_file(root, relative) as stream:
            text = stream.read().decode("utf-8")
    except UnicodeError:
        raise damaged("Drift state is not valid UTF-8.") from None
    except FileNotFoundError:
        raise
    except OSError:
        raise StorageError("Could not read Drift project state.") from None
    try:
        value = json.loads(
            text, object_pairs_hook=_unique, parse_constant=_invalid_constant
        )
        if isinstance(value, dict):
            schema = value.get("schema_version")
            if type(schema) is int and schema != 1:
                raise UnsupportedSchemaError(
                    "This Drift schema version is unsupported."
                )
        # Require that decoded strings can be encoded as UTF-8, including escaped surrogates.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return record.model_validate(value)
    except (ValueError, RecursionError, UnsafePathError):
        raise damaged("Drift state does not match the v1 schema.") from None


def _encoded[Record: StrictRecord](record: Record, model: type[Record]) -> bytes:
    try:
        checked = model.model_validate(record.model_dump())
        return (
            json.dumps(
                checked.model_dump(),
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (ValueError, UnsafePathError, ValidationError):
        raise StorageError("Could not encode valid Drift project state.") from None


def read_metadata(root: Path) -> Metadata:
    return _read_record(root, METADATA, Metadata, StorageError)


def publish_metadata(root: Path, metadata: Metadata, *, replace: bool = False) -> bool:
    return publish_file(root, METADATA, _encoded(metadata, Metadata), replace=replace)


def snapshot_ids(root: Path) -> tuple[str, ...]:
    try:
        with project_directory(root, SNAPSHOTS) as (directory, descriptor):
            names = os.listdir(
                descriptor
                if descriptor is not None and os.listdir in os.supports_fd
                else directory
            )
    except OSError:
        raise StorageError(
            "Could not list Drift snapshots. Run drift init to prepare the project."
        ) from None
    return tuple(
        sorted(
            name[:-5]
            for name in names
            if name.endswith(".json") and is_snapshot_id(name[:-5])
        )
    )


def _snapshot_path(snapshot_id: str) -> str:
    if not is_snapshot_id(snapshot_id):
        raise InvalidSnapshotError("Expected a canonical snapshot ID.")
    return f"{STATE}/snapshots/{snapshot_id}.json"


def resolve_snapshot(root: Path, reference: str) -> Snapshot:
    if not is_snapshot_reference(reference):
        raise InvalidSnapshotError("Invalid snapshot reference.")
    if is_snapshot_id(reference):
        return read_snapshot(root, reference)
    matches = [value for value in snapshot_ids(root) if value.startswith(reference)]
    if not matches:
        raise SnapshotNotFoundError("No snapshot matches that reference.")
    if len(matches) > 1:
        raise AmbiguousSnapshotError(
            "More than one snapshot matches. Use a longer prefix."
        )
    return read_snapshot(root, matches[0])


def read_snapshot(root: Path, snapshot_id: str) -> Snapshot:
    try:
        snapshot = _read_record(
            root, _snapshot_path(snapshot_id), Snapshot, InvalidSnapshotError
        )
    except FileNotFoundError:
        raise SnapshotNotFoundError("No snapshot matches that reference.") from None
    if snapshot.id != snapshot_id:
        raise InvalidSnapshotError("Snapshot ID does not match its filename.")
    return snapshot


def publish_snapshot(root: Path, snapshot: Snapshot) -> bool:
    return publish_file(root, _snapshot_path(snapshot.id), _encoded(snapshot, Snapshot))
