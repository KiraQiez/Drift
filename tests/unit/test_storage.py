import json
import os
import subprocess
import sys

import pytest

from drift import storage
from drift.collectors.base import COLLECTOR_IDS
from drift.exceptions import (
    AmbiguousSnapshotError,
    InvalidSnapshotError,
    StorageError,
    UnsafePathError,
    UnsupportedSchemaError,
)
from drift.models import Metadata, Snapshot

FIRST_ID = "a81f23d4901649b1aa477f030a879e44"
SECOND_ID = "a81f23d4901649b1aa477f030a879e45"


@pytest.fixture
def state(tmp_path):
    assert storage.ensure_directory(tmp_path, ".drift")
    assert storage.ensure_directory(tmp_path, ".drift/snapshots")
    return tmp_path


def snapshot(snapshot_id=FIRST_ID):
    return Snapshot.model_validate(
        {
            "schema_version": 1,
            "id": snapshot_id,
            "created_at": "2026-11-26T03:40:00Z",
            "message": "Working",
            "scope": {
                "active_allowlist": None,
                "active_name_case": "preserve",
                "compose_project": None,
            },
            "collectors": {
                name: {"status": "disabled", "probes": {}} for name in COLLECTOR_IDS
            },
        }
    )


def test_private_immutable_snapshots_and_reference_lookup(state):
    data = snapshot()
    assert storage.publish_snapshot(state, data)
    assert not storage.publish_snapshot(
        state, data.model_copy(update={"message": "replacement"})
    )
    assert storage.resolve_snapshot(state, "a81f23") == data
    assert storage.resolve_snapshot(state, FIRST_ID) == data
    assert storage.publish_snapshot(state, snapshot(SECOND_ID))
    with pytest.raises(AmbiguousSnapshotError):
        storage.resolve_snapshot(state, "a81f23")
    target = state / ".drift/snapshots" / f"{FIRST_ID}.json"
    assert target.read_bytes().endswith(b"\n")
    if os.name == "posix":
        assert target.stat().st_mode & 0o077 == 0
        assert target.parent.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"schema_version": 2}, UnsupportedSchemaError),
        ({"schema_version": True}, InvalidSnapshotError),
        ({"id": SECOND_ID}, InvalidSnapshotError),
        ({"created_at": "2026-11-26T03:40:00+08:00"}, InvalidSnapshotError),
        ({"message": "hidden\nline"}, InvalidSnapshotError),
        ({"unexpected": "private"}, InvalidSnapshotError),
        ({"message": "\ud800"}, InvalidSnapshotError),
    ],
)
def test_snapshot_validation_rejects_damaged_payload(state, changes, error):
    target = state / ".drift/snapshots" / f"{FIRST_ID}.json"
    target.write_text(json.dumps(snapshot().model_dump() | changes), encoding="utf-8")
    with pytest.raises(error):
        storage.read_snapshot(state, FIRST_ID)


@pytest.mark.parametrize(
    "body",
    [b'{"schema_version":1,"schema_version":1}', b'{"baseline_id":NaN}', b"\xff"],
)
def test_metadata_rejects_non_strict_json(state, body):
    (state / ".drift/metadata.json").write_bytes(body)
    with pytest.raises(StorageError):
        storage.read_metadata(state)


def test_failed_replace_keeps_metadata_and_removes_staging(state, monkeypatch):
    before = Metadata(schema_version=1, baseline_id=None)
    storage.publish_metadata(state, before)

    def fail(*args, **kwargs):
        raise OSError("sensitive filesystem error")

    monkeypatch.setattr(storage.os, "replace", fail)
    with pytest.raises(StorageError, match="safely"):
        storage.publish_metadata(
            state, Metadata(schema_version=1, baseline_id=FIRST_ID), replace=True
        )
    assert storage.read_metadata(state) == before
    assert not list((state / ".drift").glob(".drift-stage-*"))


def test_refuses_symlink_parent(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "project"
    root.mkdir()
    try:
        (root / ".drift").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks are unavailable")
    with pytest.raises(UnsafePathError):
        storage.publish_metadata(root, Metadata(schema_version=1, baseline_id=None))
    assert not list(outside.iterdir())


def test_concurrent_no_clobber_publication_returns_complete_data(state):
    code = (
        "from pathlib import Path; import sys; from drift.storage import publish_file; "
        "print(publish_file(Path(sys.argv[1]), '.drift/record', sys.argv[2].encode() * 262144))"
    )
    with subprocess.Popen(
        [sys.executable, "-c", code, str(state), "a"], stdout=subprocess.PIPE
    ) as one:
        with subprocess.Popen(
            [sys.executable, "-c", code, str(state), "b"], stdout=subprocess.PIPE
        ) as two:
            results = {
                one.communicate(timeout=15)[0].strip(),
                two.communicate(timeout=15)[0].strip(),
            }
            assert one.returncode == two.returncode == 0
    assert results == {b"True", b"False"}
    assert (state / ".drift/record").read_bytes() in (b"a" * 262144, b"b" * 262144)
