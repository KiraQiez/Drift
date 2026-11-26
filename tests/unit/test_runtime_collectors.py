from pathlib import Path
from time import monotonic

import pytest

from drift.collectors import runtime, system
from drift.collectors.base import CollectorContext, Observation, ProbeIssue
from drift.collectors.engine import run_collectors
from drift.collectors.registry import build_registry
from drift.collectors.runner import CommandOutput
from drift.config import ProjectConfig


def context(root: Path) -> CollectorContext:
    return CollectorContext(root, ProjectConfig(schema_version=1), monotonic() + 8)


def test_system_uses_macos_product_version(tmp_path, monkeypatch):
    monkeypatch.setattr(system.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(system.platform, "mac_ver", lambda: ("15.3", ("", "", ""), ""))
    monkeypatch.setattr(system.platform, "release", lambda: "24.3.0")
    monkeypatch.setattr(system.platform, "machine", lambda: "arm64")
    assert system.collect(context(tmp_path)) == {
        "os": Observation("Darwin"),
        "os_version": Observation("15.3"),
        "architecture": Observation("arm64"),
    }


def test_runtime_formats_and_go_controls(tmp_path, monkeypatch):
    outputs = {
        "python": CommandOutput(b"Python 3.14.0rc1\n", b""),
        "node": CommandOutput(b"v22.4.0\n", b""),
        "npm": CommandOutput(b"10.8.2\n", b""),
        "php": CommandOutput(b"PHP 8.4.1 (cli) (built: Apr 12 2024)\n", b""),
        "java": CommandOutput(b"", b'java version "1.8.0_452"\nother details\n'),
        "go": CommandOutput(b"go version go1.25rc1 darwin/arm64\n", b""),
    }

    def run(tool, args, *, cwd, deadline, profile):
        assert profile == ("go" if tool == "go" else "default")
        assert args == runtime._COMMANDS[tool]
        return outputs[tool]

    monkeypatch.setattr(runtime, "run_probe", run)
    result = run_collectors(
        tmp_path, context(tmp_path).config, build_registry(context(tmp_path).config)
    )
    assert result["runtime"].probes == dict(
        zip(
            runtime.PROBE_IDS,
            map(
                Observation,
                ("3.14.0rc1", "22.4.0", "10.8.2", "8.4.1", "1.8.0_452", "1.25rc1"),
            ),
            strict=True,
        )
    )


def test_runtime_failures_and_python_fallback(tmp_path, monkeypatch):
    missing = ProbeIssue("unavailable", "executable_missing")
    timeout = ProbeIssue("failed", "timeout")
    monkeypatch.setattr(
        runtime,
        "run_probe",
        lambda name, *args, **kwargs: {
            "python3": CommandOutput(b"Python 3.12.5", b""),
            "node": CommandOutput(b"unrecognized-secret", b""),
            "go": timeout,
        }.get(name, missing),
    )
    result = runtime.collect(context(tmp_path))
    assert result["python"] == Observation("3.12.5")
    assert result["node"] == ProbeIssue("failed", "invalid_output")
    assert result["go"] == timeout
    assert result["npm"] == missing


def test_windows_npm_needs_verified_companion(tmp_path, monkeypatch):
    (tmp_path / "npm.cmd").write_text("unsafe wrapper")
    (tmp_path / "node.exe").touch()
    monkeypatch.setattr(runtime, "launcher_paths", lambda: [tmp_path])
    monkeypatch.setattr(
        runtime,
        "run_probe",
        lambda *args, **kwargs: pytest.fail("must verify script first"),
    )
    assert runtime._windows_npm(context(tmp_path)) == ProbeIssue(
        "unsupported", "unsupported_launcher"
    )

    script = tmp_path / "node_modules/npm/bin/npm-cli.js"
    script.parent.mkdir(parents=True)
    script.touch()

    def launch(tool, args, **kwargs):
        assert tool == (tmp_path / "node.exe").resolve()
        assert args == (str(script.resolve()), "--version")
        return CommandOutput(b"10.2.1", b"")

    monkeypatch.setattr(runtime, "run_probe", launch)
    assert runtime._windows_npm(context(tmp_path)) == CommandOutput(b"10.2.1", b"")
