"""Manage the project-local baseline pointer."""

from pathlib import Path

from drift.exceptions import StorageError
from drift.models import Metadata
from drift.storage import publish_metadata, read_metadata, resolve_snapshot


def baseline_metadata(root: Path) -> Metadata:
    try:
        return read_metadata(root)
    except FileNotFoundError:
        raise StorageError(
            "Drift metadata is missing. Recover it or run drift init."
        ) from None


def set_baseline(root: Path, reference: str) -> str:
    snapshot = resolve_snapshot(root, reference)
    metadata = baseline_metadata(root)
    if metadata.baseline_id != snapshot.id:
        publish_metadata(
            root, Metadata(schema_version=1, baseline_id=snapshot.id), replace=True
        )
    return snapshot.id
