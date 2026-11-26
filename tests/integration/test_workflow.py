import json
import subprocess
import sys
from time import monotonic, sleep
from uuid import UUID

import pytest
from rich.console import Console
from typer.testing import CliRunner

from drift import comparison_output, snapshots, storage
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
    command = "baseline set" if args[0] == "baseline" else args[0]
    assert value["command"] == command
    assert set(value) == {
        "schema_version",
        "command",
        "error" if code == 1 else "result",
    }
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


def test_baseline_mode_initializes_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["snapshot"]).exit_code == 1
    result = runner.invoke(app, ["snapshot", "--baseline", "-m", "Working"])
    assert result.exit_code == 0, (result.output, result.exception)
    assert "Run drift verify" in result.stdout
    assert (tmp_path / "drift.toml").is_file()
    record = payload(tmp_path, "history")["snapshots"][0]
    assert record["message"] == "Working"
    assert storage.read_metadata(tmp_path).baseline_id == record["id"]


def test_baseline_mode_uses_parent_or_explicit_project(tmp_path, monkeypatch):
    root = prepare(tmp_path)
    child = root / "nested"
    child.mkdir()
    original_config = (root / "drift.toml").read_bytes()
    monkeypatch.chdir(child)

    result = runner.invoke(app, ["snapshot", "--baseline", "--json"])
    assert result.exit_code == 0, (result.output, result.exception)
    saved = json.loads(result.stdout)["result"]
    assert saved["baseline_id"] == saved["snapshot"]["id"]
    assert not (child / "drift.toml").exists()
    assert (root / "drift.toml").read_bytes() == original_config
    assert payload(root, "verify")["reference_id"] == saved["baseline_id"]

    explicit = payload(child, "snapshot", "--baseline")
    assert (child / "drift.toml").is_file()
    assert storage.read_metadata(child).baseline_id == explicit["baseline_id"]
    assert storage.read_metadata(root).baseline_id == saved["baseline_id"]


def test_baseline_mode_refreshes_the_pointer_and_keeps_history(tmp_path):
    root = prepare(tmp_path)
    first = payload(root, "snapshot", "--baseline")
    (root / "requirements.txt").write_text("example==1\n", encoding="utf-8")
    second = payload(root, "snapshot", "--baseline")
    assert second["snapshot"]["id"] == second["baseline_id"]
    assert second["baseline_id"] != first["baseline_id"]
    assert payload(root, "verify")["reference_id"] == second["baseline_id"]
    assert payload(root, "history")["snapshots"] == [
        first["snapshot"],
        second["snapshot"],
    ]
    assert set(payload(root, "snapshot")) == {"snapshot"}
    assert storage.read_metadata(root).baseline_id == second["baseline_id"]


def test_baseline_mode_keeps_the_snapshot_when_replacement_fails(tmp_path, monkeypatch):
    root = prepare(tmp_path)
    first = payload(root, "snapshot", "--baseline")

    def fail(*args, **kwargs):
        raise OSError("sensitive failure")

    monkeypatch.setattr(storage.os, "replace", fail)
    error = payload(root, "snapshot", "--baseline", code=1)
    assert error["code"] == "storage_error"
    assert "sensitive failure" not in error["message"]
    assert payload(root, "verify")["reference_id"] == first["baseline_id"]
    assert len(payload(root, "history")["snapshots"]) == 2


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


def test_baseline_help_and_setting_partial_snapshot_without_rewriting(tmp_path):
    assert "set" in invoke(tmp_path, "baseline").stdout
    assert "set" in invoke(tmp_path, "baseline", "--help").stdout
    root = prepare(tmp_path, environment=True)
    saved = take(root)
    assert saved["collector_statuses"]["environment"] == "partial"
    assert payload(root, "baseline", "set", saved["id"][:8]) == {
        "baseline_id": saved["id"]
    }
    before = project_files(root)
    assert payload(root, "baseline", "set", saved["id"]) == {"baseline_id": saved["id"]}
    missing = "a81f23d4901649b1aa477f030a879e44"
    assert (
        payload(root, "baseline", "set", missing, code=1)["code"]
        == "snapshot_not_found"
    )
    assert project_files(root) == before


def test_failed_baseline_publication_preserves_pointer(tmp_path, monkeypatch):
    root = prepare(tmp_path)
    before, after = take(root), take(root)
    payload(root, "baseline", "set", before["id"])
    initial_state = project_files(root)

    def fail(*args, **kwargs):
        raise OSError("sensitive failure")

    monkeypatch.setattr(storage.os, "replace", fail)
    assert (
        payload(root, "baseline", "set", after["id"], code=1)["code"] == "storage_error"
    )
    assert project_files(root) == initial_state


def test_readers_observe_valid_baselines_during_updates(tmp_path):
    root = prepare(tmp_path)
    first, second = (take(root)["id"] for _ in range(2))
    payload(root, "baseline", "set", first)
    code = (
        "from pathlib import Path; import sys; from drift.baseline import set_baseline; "
        "root=Path(sys.argv[1]); [set_baseline(root, snapshot) for snapshot in sys.argv[2:] * 10]"
    )
    deadline = monotonic() + 15
    with subprocess.Popen(
        [sys.executable, "-c", code, str(root), second, first]
    ) as writer:
        while writer.poll() is None and monotonic() < deadline:
            assert storage.read_metadata(root).baseline_id in {first, second}
            sleep(0.002)
        assert writer.wait(timeout=1) == 0
    assert storage.read_metadata(root).baseline_id == first


def test_verify_match_then_drift_from_full_workflow(tmp_path):
    root = prepare(tmp_path)
    manifest = root / "requirements.txt"
    manifest.write_text("example==1\n")
    saved = take(root, "-m", "Known working")
    assert payload(root, "history")["snapshots"] == [saved]
    assert payload(root, "show", saved["id"])["snapshot"]["message"] == "Known working"
    payload(root, "baseline", "set", saved["id"])
    assert payload(root, "diff")["outcome"] == "match"
    assert payload(root, "verify")["outcome"] == "match"
    manifest.write_text("example==2\n")
    before = project_files(root)
    result = payload(root, "verify", code=3)
    assert result == payload(root, "diff", saved["id"], code=3)
    assert result["reference_id"] == saved["id"]
    assert result["changes"][0]["probe"] == "manifest:requirements.txt"
    assert result["changes"][0]["kind"] == "modified"
    assert result == payload(root, "verify", "--details", code=3)
    plain = invoke(root, "verify", code=3).stdout
    assert "Drift detected" in plain
    assert len(plain.splitlines()) == 3
    assert "Known working" in plain
    before_hash = result["changes"][0]["before"]
    assert before_hash[:12] + "…" in plain
    assert before_hash not in plain and "\x1b" not in plain
    detailed = invoke(root, "diff", "--details", code=3).stdout
    assert before_hash in detailed
    assert "Git reference (disabled)" in detailed
    assert project_files(root) == before


@pytest.mark.parametrize(
    ("width", "no_color", "table"),
    [(100, False, True), (55, False, False), (100, True, False)],
)
def test_comparison_terminal_layout(tmp_path, monkeypatch, width, no_color, table):
    root = prepare(tmp_path, environment=True)
    saved = take(root, "-m", "[bold]Working[/bold]")
    payload(root, "baseline", "set", saved["id"])
    if no_color:
        monkeypatch.setenv("NO_COLOR", "1")
    else:
        monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        comparison_output,
        "Console",
        lambda *, file, force_terminal: Console(
            file=file, force_terminal=True, width=width, _environ={"TERM": "xterm"}
        ),
    )
    incomplete = invoke(root, "verify", code=4).stdout
    assert "Comparison incomplete" in incomplete
    assert "not found" in incomplete
    (root / "requirements.txt").write_text("example==1\n")
    output = invoke(root, "verify", code=3).stdout
    assert ("Before" in output and "Now" in output) is table
    assert ("\x1b[" in output) is table
    assert "[bold]Working[/bold]" in output
    assert "requirements.txt" in output and "Coverage gap" in output
    assert "Git reference" not in output


def test_verify_gaps_and_confirmed_drift_precedence(tmp_path):
    root = prepare(tmp_path, environment=True)
    saved = take(root)
    payload(root, "baseline", "set", saved["id"])
    incomplete = payload(root, "verify", code=4)
    assert incomplete["outcome"] == "incomplete"
    assert incomplete["gaps"] == [
        {
            "collector": "environment",
            "probe": "file:missing.env",
            "side": "both",
            "code": "not_found",
        }
    ]
    (root / "requirements.txt").write_text("example==1\n")
    drift = payload(root, "verify", code=3)
    assert drift["outcome"] == "drift"
    assert drift["gaps"] == incomplete["gaps"]


def test_verify_unset_missing_and_damaged_baselines(tmp_path):
    root = prepare(tmp_path)
    assert payload(root, "verify", code=1)["code"] == "baseline_missing"
    result = invoke(root, "verify", code=1)
    assert not result.stdout and "baseline_missing" in result.stderr
    saved = take(root)
    payload(root, "baseline", "set", saved["id"])
    target = root / ".drift/snapshots" / f"{saved['id']}.json"
    target.write_text("sensitive malformed text")
    assert payload(root, "verify", code=1)["code"] == "invalid_baseline"
    target.unlink()
    assert payload(root, "verify", code=1)["code"] == "invalid_baseline"
    (root / ".drift/metadata.json").write_text("damaged")
    assert payload(root, "verify", code=1)["code"] == "storage_error"
