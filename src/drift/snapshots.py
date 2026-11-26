"""Capture and describe environment snapshots."""

import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from drift.collectors.engine import run_collectors
from drift.collectors.registry import build_registry
from drift.config import ProjectConfig
from drift.exceptions import (
    HistoryEmptyError,
    HistoryIncompleteError,
    InvalidSnapshotError,
    SnapshotNotFoundError,
    StorageError,
    UnsafePathError,
    UnsupportedSchemaError,
)
from drift.models import CapturedEnvironment, Scope, Snapshot
from drift.storage import publish_snapshot, read_snapshot, snapshot_ids


def capture(root: Path, config: ProjectConfig) -> CapturedEnvironment:
    allowlist = config.environment.active_allowlist
    scope = Scope(
        active_allowlist=None if allowlist is None else sorted(allowlist),
        active_name_case="uppercase" if os.name == "nt" else "preserve",
        compose_project=config.docker.compose_project,
    )
    results = run_collectors(root, config, build_registry(config))
    return CapturedEnvironment.model_validate(
        {
            "scope": scope,
            "collectors": {name: asdict(result) for name, result in results.items()},
        }
    )


def capture_snapshot(
    root: Path, config: ProjectConfig, message: str | None
) -> Snapshot:
    current = capture(root, config)
    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    for _ in range(8):
        snapshot = Snapshot(
            schema_version=1,
            id=uuid4().hex,
            created_at=timestamp,
            message=message,
            scope=current.scope,
            collectors=current.collectors,
        )
        if publish_snapshot(root, snapshot):
            return snapshot
    raise StorageError("Could not allocate a unique snapshot ID.")


def summary(snapshot: Snapshot) -> dict[str, object]:
    return {
        "id": snapshot.id,
        "created_at": snapshot.created_at,
        "message": snapshot.message,
        "collector_statuses": {
            name: result.status for name, result in snapshot.collectors.items()
        },
    }


@dataclass(frozen=True)
class History:
    snapshots: list[Snapshot]
    damaged: list[dict[str, str]]


def _chronological(snapshot: Snapshot) -> tuple[datetime, str, str]:
    timestamp = datetime.fromisoformat(snapshot.created_at).replace(microsecond=0)
    fraction = snapshot.created_at.removesuffix("Z").partition(".")[2].rstrip("0")
    return timestamp, fraction, snapshot.id


def list_history(root: Path) -> History:
    readable: list[Snapshot] = []
    damaged: list[dict[str, str]] = []
    for snapshot_id in snapshot_ids(root):
        try:
            readable.append(read_snapshot(root, snapshot_id))
        except SnapshotNotFoundError:
            damaged.append({"id": snapshot_id, "code": "storage_error"})
        except (
            InvalidSnapshotError,
            UnsupportedSchemaError,
            UnsafePathError,
            StorageError,
        ) as error:
            damaged.append({"id": snapshot_id, "code": error.code})
    return History(sorted(readable, key=_chronological), damaged)


def latest_snapshot(root: Path) -> Snapshot:
    history = list_history(root)
    if history.damaged:
        raise HistoryIncompleteError(
            "History contains damaged entries. Run drift history or select a snapshot explicitly."
        )
    if not history.snapshots:
        raise HistoryEmptyError("There are no snapshots. Run drift snapshot first.")
    return history.snapshots[-1]
