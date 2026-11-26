"""Manage the project-local baseline pointer."""

from pathlib import Path

from drift.exceptions import (
    BaselineMissingError,
    DriftError,
    InvalidBaselineError,
    StorageError,
)
from drift.models import Metadata, Snapshot
from drift.storage import (
    publish_metadata,
    read_metadata,
    read_snapshot,
    resolve_snapshot,
)


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


def baseline_snapshot(root: Path) -> Snapshot:
    baseline_id = baseline_metadata(root).baseline_id
    if baseline_id is None:
        raise BaselineMissingError(
            "Save a baseline with drift snapshot --baseline or select a saved snapshot with drift baseline set SNAPSHOT."
        )
    try:
        return read_snapshot(root, baseline_id)
    except DriftError:
        raise InvalidBaselineError(
            "The baseline snapshot is missing or unreadable. Select a valid snapshot with drift baseline set."
        ) from None
