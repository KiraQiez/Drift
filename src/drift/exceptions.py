"""Errors with stable codes and safe user-facing messages."""

from typing import ClassVar


class DriftError(Exception):
    """An expected Drift error."""

    code: ClassVar[str]


class InvalidProjectError(DriftError):
    code = "invalid_project"


class ProjectNotInitializedError(DriftError):
    code = "project_not_initialized"


class InvalidConfigError(DriftError):
    code = "invalid_config"


class UnsupportedSchemaError(DriftError):
    code = "unsupported_schema"


class UnsafePathError(DriftError):
    code = "unsafe_path"


class StorageError(DriftError):
    code = "storage_error"


class InvalidSnapshotError(DriftError):
    code = "invalid_snapshot"


class SnapshotNotFoundError(DriftError):
    code = "snapshot_not_found"


class AmbiguousSnapshotError(DriftError):
    code = "ambiguous_snapshot"
