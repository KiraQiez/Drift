"""Prepare and resolve project-local Drift state."""

from pathlib import Path

from drift.config import CONFIG_NAME, ProjectConfig, load_config, resolve_project_root
from drift.exceptions import ProjectNotInitializedError, StorageError
from drift.models import Metadata
from drift.paths import project_directory
from drift.storage import (
    SNAPSHOTS,
    STATE,
    ensure_directory,
    publish_file,
    publish_metadata,
    read_metadata,
    snapshot_ids,
)

_DEFAULT_CONFIG = b"schema_version = 1\n"
_IGNORE = b"/*\n!/.gitignore\n"


def _ensure_metadata(root: Path) -> bool:
    try:
        read_metadata(root)
    except FileNotFoundError:
        if snapshot_ids(root):
            try:
                read_metadata(root)  # A concurrent initializer may have completed.
            except FileNotFoundError:
                raise StorageError(
                    "Snapshot history exists without metadata. Recover metadata before initializing."
                ) from None
            return False
        if publish_metadata(root, Metadata(schema_version=1, baseline_id=None)):
            return True
        read_metadata(root)
    return False


def initialize(project: Path | None) -> bool:
    root = resolve_project_root(project, search_parents=False)
    try:
        load_config(root)
    except ProjectNotInitializedError:
        config_missing = True
    else:
        config_missing = False

    created = ensure_directory(root, STATE)
    created |= ensure_directory(root, "/".join(SNAPSHOTS))
    created |= _ensure_metadata(root)
    created |= publish_file(root, f"{STATE}/.gitignore", _IGNORE)
    if config_missing:
        published = publish_file(root, CONFIG_NAME, _DEFAULT_CONFIG)
        if not published:
            load_config(root)
        created |= published
    return created


def initialized_project(project: Path | None) -> tuple[Path, ProjectConfig]:
    root = resolve_project_root(project)
    config = load_config(root)
    try:
        with project_directory(root, SNAPSHOTS):
            pass
    except OSError:
        raise StorageError(
            "Drift project state is incomplete. Run drift init."
        ) from None
    return root, config


def prepare_baseline_project(project: Path | None) -> tuple[Path, ProjectConfig]:
    """Find the existing project or prepare the selected directory for a baseline."""
    try:
        root = resolve_project_root(project)
    except ProjectNotInitializedError:
        root = resolve_project_root(project, search_parents=False)
    initialize(root)
    return initialized_project(root)
