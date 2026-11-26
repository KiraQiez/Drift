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


def project_files(root):
    return {
        str(file.relative_to(root)): (file.read_bytes(), file.stat().st_mtime_ns)
        for file in root.rglob("*")
        if file.is_file()
    }


def test_history_ordering_and_partial_damage(tmp_path):
    root = prepare(tmp_path)
    assert payload(root, "history") == {"snapshots": [], "damaged": []}
    first, second, third = (take(root) for _ in range(3))
    first_path = root / ".drift/snapshots" / f"{first['id']}.json"
    second_path = root / ".drift/snapshots" / f"{second['id']}.json"
    record = json.loads(first_path.read_bytes())
    record["created_at"] = "2026-11-26T03:40:00.1000001Z"
    first_path.write_text(json.dumps(record))
    record = json.loads(second_path.read_bytes())
    record["created_at"] = "2026-11-26T03:40:00.1Z"
    second_path.write_text(json.dumps(record))
    (root / ".drift/snapshots" / f"{third['id']}.json").write_text("damaged sentinel")
    (root / ".drift/snapshots/.drift-stage-old").touch()
    before = project_files(root)
    result = payload(root, "history", code=4)
    assert [item["id"] for item in result["snapshots"]] == [second["id"], first["id"]]
    assert result["damaged"] == [{"id": third["id"], "code": "invalid_snapshot"}]
    assert payload(root, "show", first["id"][:8])["snapshot"]["id"] == first["id"]
    assert payload(root, "show", third["id"], code=1)["code"] == "invalid_snapshot"
    assert project_files(root) == before


def test_show_validates_reference_and_renders_literal_data(tmp_path):
    root = prepare(tmp_path)
    record = take(root, "-m", "A [literal] note")
    result = invoke(root, "show", record["id"])
    assert "A [literal] note" in result.stdout
    assert "dependency" in result.stdout
    malformed = invoke(root, "show", "../secret", "--json", code=2)
    assert not malformed.stdout
    assert "../secret" not in malformed.stderr


def test_diff_uses_latest_or_explicit_reference_read_only(tmp_path):
    root = prepare(tmp_path)
    assert payload(root, "diff", code=1)["code"] == "history_empty"
    first = take(root)
    (root / "requirements.txt").write_text("sample==1\n")
    second = take(root)
    before = project_files(root)
    latest = payload(root, "diff")
    assert latest["reference_id"] == second["id"]
    assert latest["outcome"] == "match"
    old = payload(root, "diff", first["id"][:8], code=3)
    assert old["reference_id"] == first["id"]
    assert old["outcome"] == "drift"
    assert old["changes"][0]["probe"] == "manifest:requirements.txt"
    assert old["changes"][0]["kind"] == "added"
    assert project_files(root) == before


def test_damaged_entry_blocks_automatic_diff_only(tmp_path):
    root = prepare(tmp_path)
    first, damaged = take(root), take(root)
    (root / ".drift/snapshots" / f"{damaged['id']}.json").write_text("damaged")
    assert payload(root, "diff", code=1)["code"] == "history_incomplete"
    assert payload(root, "diff", first["id"])["outcome"] == "match"
    assert payload(root, "diff", damaged["id"], code=1)["code"] == "invalid_snapshot"
