from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from drift.cli import app

runner = CliRunner()


@pytest.mark.parametrize("args", [[], ["--help"], ["--project", "missing", "--help"]])
def test_root_help(
    args: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, args)

    assert result.exit_code == 0
    assert "Usage:" in result.stdout
    assert "--help" in result.stdout
    assert "--version" in result.stdout
    assert "--project" in result.stdout
    assert result.stderr == ""
    assert not list(tmp_path.iterdir())


def test_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["--project", "missing", "--version"])

    assert result.exit_code == 0
    assert result.stdout == f"drift {version('drift-dev-env')}\n"
    assert result.stderr == ""
    assert not list(tmp_path.iterdir())


def test_unknown_option_uses_stderr() -> None:
    result = runner.invoke(app, ["--unknown"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "--unknown" in result.stderr
