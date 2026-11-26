import json
import subprocess
import sys
from uuid import UUID

from typer.testing import CliRunner

from drift import snapshots, storage
from drift.cli import app

runner = CliRunner()


def invoke(root, *args, code=0):
    result = runner.invoke(app, ["--project", str(root), *args])
    assert result.exit_code == code, (result.output, result.exception)
    return result


def payload(root, *args, code=0):
    result = invoke(root, *args, "--json", code=code)
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1
    value = json.loads(result.stdout)
    assert value["schema_version"] == 1
    return value.get("result", value.get("error"))


def prepare(root, *, environment=False):
    assert payload(root, "init") == {"created": True}
    (root / "drift.toml").write_text(
        "schema_version = 1\n[collectors]\nsystem=false\nruntime=false\ndocker=false\n"
        f"environment={str(environment).lower()}\ngit=false\n"
        '[environment]\nfiles=["missing.env"]\nactive_allowlist=[]\n',
        encoding="utf-8",
    )
    return root


def take(root, *args):
    return payload(root, "snapshot", *args)["snapshot"]


def test_snapshot_preserves_partial_results_and_retries_collision(
    tmp_path, monkeypatch
):
    root = prepare(tmp_path, environment=True)
    (root / "requirements.txt").write_text("test==1")
    first = take(root, "--message", "Working [env] λ")
    duplicate, replacement = UUID(first["id"]), UUID("a81f23d4901649b1aa477f030a879e44")
    identifiers = iter((duplicate, replacement))
    monkeypatch.setattr(snapshots, "uuid4", lambda: next(identifiers))
    second = take(root)
    assert first["collector_statuses"]["environment"] == "partial"
    assert first["message"] == "Working [env] λ"
    assert second["id"] == replacement.hex
    record = storage.read_snapshot(root, first["id"])
    assert (
        record.collectors["environment"].probes["file:missing.env"].status
        == "unavailable"
    )
    assert len(storage.snapshot_ids(root)) == 2


def test_snapshot_rejects_controls_before_collecting(tmp_path):
    root = prepare(tmp_path)
    result = invoke(root, "snapshot", "-m", "secret\x1b", "--json", code=2)
    assert not result.stdout
    assert "secret" not in result.stderr
    assert not storage.snapshot_ids(root)


def test_parallel_snapshot_invocations_publish_separate_records(tmp_path):
    root = prepare(tmp_path)
    command = [
        sys.executable,
        "-c",
        "from drift.cli import app; app()",
        "--project",
        str(root),
        "snapshot",
        "--json",
    ]
    with (
        subprocess.Popen(command, stdout=subprocess.PIPE) as first,
        subprocess.Popen(command, stdout=subprocess.PIPE) as second,
    ):
        ids = {
            json.loads(child.communicate(timeout=20)[0])["result"]["snapshot"]["id"]
            for child in (first, second)
        }
        assert first.returncode == second.returncode == 0
    assert len(ids) == 2 and ids == set(storage.snapshot_ids(root))
