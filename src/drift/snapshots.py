"""Capture and describe environment snapshots."""

import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from drift.collectors.engine import run_collectors
from drift.collectors.registry import build_registry
from drift.config import ProjectConfig
from drift.exceptions import StorageError
from drift.models import CapturedEnvironment, Scope, Snapshot
from drift.storage import publish_snapshot


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
