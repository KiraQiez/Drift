import json
import os
import subprocess

import pytest
from typer.testing import CliRunner

from drift.cli import app
from drift.collectors import runtime
from drift.collectors.runner import CommandOutput

runner = CliRunner()


def test_cli_reports_and_state_exclude_synthetic_secrets(tmp_path, monkeypatch):
    active = "audit-active-value-271"
    declared = "audit-declared-value-314"
    malformed = "audit-invalid-line-592"
    command_out = "audit-command-stdout-653"
    command_err = "audit-command-stderr-589"
    monkeypatch.setenv("DRIFT_AUDIT_ACTIVE", active)
    (tmp_path / "fixture.env").write_text(f"FILE_TOKEN={declared}\n", encoding="utf-8")
    (tmp_path / "invalid.env").write_text(malformed, encoding="utf-8")
    (tmp_path / "drift.toml").write_text(
        "schema_version = 1\n[collectors]\nsystem=false\ndocker=false\ngit=false\n"
        '[environment]\nfiles=["fixture.env", "invalid.env"]\n'
        'active_allowlist=["DRIFT_AUDIT_ACTIVE"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime,
        "run_probe",
        lambda *args, **kwargs: CommandOutput(
            command_out.encode(), f"\x1b[31m{command_err}".encode()
        ),
    )
    reports = []

    def run(*args, code=0):
        result = runner.invoke(app, ["--project", str(tmp_path), *args])
        assert result.exit_code == code, result.output
        reports.extend((result.stdout, result.stderr))
        return result

    run("init", "--json")
    snapshot = json.loads(run("snapshot", "--json").stdout)["result"]["snapshot"]
    snapshot_id = snapshot["id"]
    data = json.loads(run("show", snapshot_id, "--json").stdout)["result"]["snapshot"]
    environment = data["collectors"]["environment"]["probes"]
    assert environment["active"]["value"] == ["DRIFT_AUDIT_ACTIVE"]
    assert environment["file:fixture.env"]["value"] == ["FILE_TOKEN"]
    assert environment["file:invalid.env"] == {
        "status": "failed",
        "code": "invalid_input",
    }
    assert data["collectors"]["runtime"]["status"] == "failed"
    run("show", snapshot_id)
    run("baseline", "set", snapshot_id, "--json")
    run("verify", "--json", code=4)
    run("verify", code=4)
    run("history", "--json")

    for path in (tmp_path / ".drift").rglob("*"):
        if path.is_file():
            reports.append(path.read_text(encoding="utf-8"))
    combined = "\n".join(reports)
    for secret in (active, declared, malformed, command_out, command_err):
        assert secret not in combined
    assert "\x1b" not in combined


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction")
def test_init_rejects_native_windows_junction_without_writing_outside(tmp_path):
    outside = tmp_path / "external"
    outside.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    junction = project / ".drift"
    subprocess.run(
        [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            "mklink",
            "/J",
            str(junction),
            str(outside),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    assert junction.is_junction()

    result = runner.invoke(app, ["--project", str(project), "init", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "unsafe_path"
    assert not list(outside.iterdir())
    assert not (project / "drift.toml").exists()
