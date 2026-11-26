import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path


def test_installed_console_workflow(tmp_path):
    executable = os.environ.get("DRIFT_TEST_EXECUTABLE") or Path(
        sys.executable
    ).with_name("drift.exe" if os.name == "nt" else "drift")
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    project = tmp_path / "project with spaces"
    child = project / "nested"
    child.mkdir(parents=True)
    manifest = project / "requirements.txt"

    def run(*args, code=0):
        result = subprocess.run(
            [str(executable), *args],
            cwd=child,
            capture_output=True,
            encoding="utf-8",
            timeout=15,
        )
        assert result.returncode == code, (result.stdout, result.stderr)
        return result

    def payload(command, *args, code=0, project_options=()):
        result = run(*project_options, *command.split(), *args, "--json", code=code)
        assert result.stderr == ""
        assert result.stdout.count("\n") == 1
        data = json.loads(result.stdout)
        key = "error" if code == 1 else "result"
        assert set(data) == {"schema_version", "command", key}
        assert data["schema_version"] == 1 and data["command"] == command
        return data[key]

    help_text = run("--help").stdout
    assert all(name in help_text for name in ("history", "baseline", "verify"))
    assert run("--version").stdout.strip() == f"drift {version}"
    assert (
        payload("history", code=1, project_options=("--project", "."))["code"]
        == "project_not_initialized"
    )
    assert payload("init", project_options=("--project", "..")) == {"created": True}
    assert not (child / "drift.toml").exists()
    (project / "drift.toml").write_text(
        "schema_version = 1\n[collectors]\nsystem=false\nruntime=false\ndocker=false\n"
        "environment=false\ngit=false\n",
        encoding="utf-8",
    )
    manifest.write_text("fixture==1\n", encoding="utf-8")
    saved = payload("snapshot", "-m", "Working [fixture]")["snapshot"]
    assert set(saved) == {"id", "created_at", "message", "collector_statuses"}
    assert payload("history") == {"snapshots": [saved], "damaged": []}
    shown = payload("show", saved["id"][:8])["snapshot"]
    assert set(shown) == {
        "schema_version",
        "id",
        "created_at",
        "message",
        "scope",
        "collectors",
    }
    assert shown["id"] == saved["id"]
    assert payload("baseline set", saved["id"]) == {"baseline_id": saved["id"]}
    matches = payload("verify")
    assert set(matches) == {
        "reference_id",
        "outcome",
        "changes",
        "gaps",
        "warnings",
        "git",
    }
    assert matches["outcome"] == "match" and matches["changes"] == []
    assert matches == payload("diff")

    manifest.write_text("fixture==2\n", encoding="utf-8")
    drift = payload("verify", code=3)
    assert drift["outcome"] == "drift" and len(drift["changes"]) == 1
    change = drift["changes"][0]
    assert set(change) == {"collector", "probe", "subject", "kind", "before", "after"}
    assert (
        change["probe"] == "manifest:requirements.txt" and change["kind"] == "modified"
    )

    config = project / "drift.toml"
    with config.open("a", encoding="utf-8") as stream:
        stream.write("dependency=false\n")
    incomplete = payload("verify", code=4)
    assert incomplete["outcome"] == "incomplete"
    assert incomplete["gaps"] == [
        {
            "collector": "dependency",
            "probe": None,
            "side": "current",
            "code": "scope_changed",
        }
    ]
    assert incomplete["warnings"] == ["no_comparable_observations"]
    invalid = run("show", "../private", "--json", code=2)
    assert not invalid.stdout and "../private" not in invalid.stderr
    assert "Compare" in run("diff", "--help").stdout
