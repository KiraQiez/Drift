import json
import shutil
import subprocess
import sys

from typer.testing import CliRunner

from drift.cli import app

runner = CliRunner()


def test_init_is_idempotent_and_preserves_custom_files(tmp_path):
    config = tmp_path / "drift.toml"
    config.write_bytes(b"schema_version = 1\n# existing config\n")
    args = ["--project", str(tmp_path), "init", "--json"]
    first = runner.invoke(app, args)
    assert first.exit_code == 0
    assert json.loads(first.stdout)["result"] == {"created": True}
    assert config.read_bytes().endswith(b"# existing config\n")
    ignore = tmp_path / ".drift/.gitignore"
    assert ignore.read_bytes() == b"/*\n!/.gitignore\n"
    ignore.write_bytes(b"# custom rules\n")
    second = runner.invoke(app, args)
    assert second.exit_code == 0
    assert json.loads(second.stdout)["result"] == {"created": False}
    assert ignore.read_bytes() == b"# custom rules\n"


def test_init_completes_partial_state_and_refuses_missing_metadata_with_history(
    tmp_path,
):
    state = tmp_path / ".drift"
    state.mkdir()
    args = ["--project", str(tmp_path), "init", "--json"]
    assert runner.invoke(app, args).exit_code == 0
    (state / "metadata.json").unlink()
    (state / "snapshots/a81f23d4901649b1aa477f030a879e44.json").write_text("{}")
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "storage_error"
    assert not (state / "metadata.json").exists()


def test_init_leaves_invalid_config_and_project_untouched(tmp_path):
    (tmp_path / "drift.toml").write_text("private content")
    result = runner.invoke(app, ["--project", str(tmp_path), "init", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "invalid_config"
    assert "private" not in result.stdout
    assert not (tmp_path / ".drift").exists()


def test_concurrent_init_and_git_exclusion(tmp_path):
    code = (
        "from pathlib import Path; import sys; from drift.project import initialize; "
        "initialize(Path(sys.argv[1]))"
    )
    command = [sys.executable, "-c", code, str(tmp_path)]
    with subprocess.Popen(command) as first, subprocess.Popen(command) as second:
        assert first.wait(timeout=15) == second.wait(timeout=15) == 0
    assert json.loads((tmp_path / ".drift/metadata.json").read_bytes()) == {
        "schema_version": 1,
        "baseline_id": None,
    }
    assert not list(tmp_path.rglob(".drift-stage-*"))
    if executable := shutil.which("git"):
        subprocess.run(
            [executable, "init", "--quiet", "--template="],
            cwd=tmp_path,
            check=True,
            timeout=10,
        )
        result = subprocess.run(
            [executable, "check-ignore", ".drift/metadata.json"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            timeout=10,
        )
        assert result.stdout.strip() == b".drift/metadata.json"
