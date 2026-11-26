import hashlib
from time import monotonic

import pytest

from drift.collectors import dependency, environment
from drift.collectors.base import CollectorContext, Observation, ProbeIssue
from drift.collectors.engine import run_collectors
from drift.collectors.registry import build_registry
from drift.config import ProjectConfig


def test_active_and_declared_names_are_independent(tmp_path, monkeypatch):
    config = ProjectConfig.model_validate(
        {
            "schema_version": 1,
            "environment": {
                "files": ["config.env", "absent.env"],
                "active_allowlist": ["ACTIVE", "MISSING"],
            },
        }
    )
    env_file = tmp_path / "config.env"
    env_file.write_bytes(
        b'# comment\r\nexport FILE_KEY = "first line\r\n'
        b'FALSE_DECLARATION=secret\r\nlast \\"quoted\\" line" # comment\r\n'
        b"EMPTY=\r\nDUPLICATE=yes\r\nDUPLICATE=no\r\n"
    )
    monkeypatch.setenv("ACTIVE", "first-secret")
    monkeypatch.setenv("EXCLUDED", "secret")
    registry = build_registry(config)
    first = run_collectors(tmp_path, config, {"environment": registry["environment"]})
    monkeypatch.setenv("ACTIVE", "second-secret")
    env_file.write_bytes(env_file.read_bytes().replace(b"first line", b"changed value"))
    second = run_collectors(tmp_path, config, {"environment": registry["environment"]})

    assert first == second
    assert first["environment"].probes == {
        "active": Observation(["ACTIVE"]),
        "file:absent.env": ProbeIssue("unavailable", "not_found"),
        "file:config.env": Observation(["DUPLICATE", "EMPTY", "FILE_KEY"]),
    }


@pytest.mark.parametrize(
    "content",
    [b"bare-name", b"NAME='unterminated", b'NAME="value" trailing', b"KEY=\xff"],
)
def test_invalid_declarations_fail_safely(tmp_path, content):
    (tmp_path / "config.env").write_bytes(content)
    config = ProjectConfig.model_validate(
        {"schema_version": 1, "environment": {"files": ["config.env"]}}
    )
    result = environment.collect(CollectorContext(tmp_path, config, monotonic() + 8))
    assert result["file:config.env"] == ProbeIssue("failed", "invalid_input")


def test_file_size_caps_and_expired_budget(tmp_path, monkeypatch):
    config = ProjectConfig.model_validate(
        {"schema_version": 1, "environment": {"files": ["vars.env"]}}
    )
    (tmp_path / "vars.env").write_bytes(b"NAME=value")
    (tmp_path / "go.mod").write_bytes(b"module example")
    monkeypatch.setattr(environment, "_FILE_LIMIT", 4)
    monkeypatch.setattr(dependency, "_FILE_LIMIT", 4)
    context = CollectorContext(tmp_path, config, monotonic() + 8)
    assert environment.collect(context)["file:vars.env"] == ProbeIssue(
        "failed", "size_limit"
    )
    assert dependency.collect(context)["manifest:go.mod"] == ProbeIssue(
        "failed", "size_limit"
    )
    expired = CollectorContext(tmp_path, config, monotonic())
    assert all(
        item == ProbeIssue("failed", "timeout")
        for item in dependency.collect(expired).values()
    )


def test_hashes_known_files_and_reports_links(tmp_path):
    content = b"module example"
    (tmp_path / "go.mod").write_bytes(content)
    (tmp_path / "hidden").write_bytes(b"must not hash")
    try:
        (tmp_path / "go.sum").symlink_to(tmp_path / "hidden")
    except OSError:
        pytest.skip("Symlinks are unavailable")
    context = CollectorContext(
        tmp_path, ProjectConfig(schema_version=1), monotonic() + 8
    )
    result = dependency.collect(context)
    assert set(result) == set(dependency.PROBE_IDS)
    assert result["manifest:go.mod"] == Observation(hashlib.sha256(content).hexdigest())
    assert result["manifest:go.sum"] == ProbeIssue("failed", "unsafe_path")
    assert result["manifest:uv.lock"] == ProbeIssue("unavailable", "not_found")


def test_detects_replaced_manifest(tmp_path, monkeypatch):
    manifest = tmp_path / "go.mod"
    manifest.write_bytes(b"module original")
    signature = dependency._signature
    calls = 0

    def replace_after_open(stream):
        nonlocal calls
        result = signature(stream)
        calls += 1
        if calls == 2:
            replacement = tmp_path / "replacement"
            replacement.write_bytes(b"module changed!")
            replacement.replace(manifest)
        return result

    monkeypatch.setattr(dependency, "_signature", replace_after_open)
    result = dependency.collect(
        CollectorContext(tmp_path, ProjectConfig(schema_version=1), monotonic() + 8)
    )
    assert result["manifest:go.mod"] == ProbeIssue("failed", "input_changed")
