import os
from pathlib import Path

import pytest

from drift.config import load_config, resolve_project_root
from drift.exceptions import (
    DriftError,
    InvalidConfigError,
    InvalidProjectError,
    ProjectNotInitializedError,
    UnsafePathError,
    UnsupportedSchemaError,
)


def test_config_defaults(tmp_path: Path) -> None:
    (tmp_path / "drift.toml").write_text("schema_version = 1\n", encoding="utf-8")

    config = load_config(tmp_path)

    assert config.schema_version == 1
    assert config.collectors.model_dump() == dict.fromkeys(
        ["system", "runtime", "docker", "environment", "dependency", "git"], True
    )
    assert config.environment.files == []
    assert config.environment.active_allowlist is None
    assert config.docker.compose_project is None


def test_config_overrides(tmp_path: Path) -> None:
    (tmp_path / "drift.toml").write_text(
        """schema_version = 1
[collectors]
docker = false
[environment]
files = ["config/.env", ".env.example"]
active_allowlist = []
[docker]
compose_project = "demo_app-1"
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert not config.collectors.docker
    assert config.collectors.runtime
    assert config.environment.files == ["config/.env", ".env.example"]
    assert config.environment.active_allowlist == []
    assert config.docker.compose_project == "demo_app-1"
    assert not (tmp_path / "config").exists()


@pytest.mark.parametrize(
    ("text", "error_type", "code"),
    [
        (b"", InvalidConfigError, "invalid_config"),
        (b'schema_version = "1"', InvalidConfigError, "invalid_config"),
        (b"schema_version = true", InvalidConfigError, "invalid_config"),
        (b"schema_version = 1.0", InvalidConfigError, "invalid_config"),
        (b"schema_version = 2", UnsupportedSchemaError, "unsupported_schema"),
        (b"schema_version = 1\n\xff", InvalidConfigError, "invalid_config"),
        (
            b"schema_version = 1\nsecret-sentinel = [",
            InvalidConfigError,
            "invalid_config",
        ),
        (
            b"schema_version = 1\nsecret-sentinel = true",
            InvalidConfigError,
            "invalid_config",
        ),
        (
            b"schema_version = 1\nschema_version = 1",
            InvalidConfigError,
            "invalid_config",
        ),
        (
            b"schema_version = 1\n[collectors]\nsystem = 1",
            InvalidConfigError,
            "invalid_config",
        ),
        (
            b"schema_version = 1\n[docker]\ncompose_project = 'Bad'",
            InvalidConfigError,
            "invalid_config",
        ),
        (
            b'schema_version = 1\n[docker]\ncompose_project = "ok\\n"',
            InvalidConfigError,
            "invalid_config",
        ),
        (
            b"schema_version = 1\n[environment]\nfiles = '.env'",
            InvalidConfigError,
            "invalid_config",
        ),
        (
            b"schema_version = 1\n[environment]\nfiles = ['.env', '.env']",
            InvalidConfigError,
            "invalid_config",
        ),
        (
            b"schema_version = 1\n[environment]\nfiles = ['../secret-sentinel']",
            UnsafePathError,
            "unsafe_path",
        ),
        (
            b"schema_version = 1\n[environment]\nactive_allowlist = ['A', 'A']",
            InvalidConfigError,
            "invalid_config",
        ),
        (
            b"schema_version = 1\n[environment]\nactive_allowlist = ['A=secret-sentinel']",
            InvalidConfigError,
            "invalid_config",
        ),
    ],
)
def test_invalid_config_has_sanitized_error(
    tmp_path: Path, text: bytes, error_type: type[DriftError], code: str
) -> None:
    (tmp_path / "drift.toml").write_bytes(text)

    with pytest.raises(error_type) as error:
        load_config(tmp_path)

    assert error.value.code == code
    assert "secret-sentinel" not in str(error.value)


def test_config_allowlist_uses_platform_case(tmp_path: Path) -> None:
    (tmp_path / "drift.toml").write_text(
        "schema_version = 1\n[environment]\nactive_allowlist = ['Path']",
        encoding="utf-8",
    )

    assert load_config(tmp_path).environment.active_allowlist == [
        "PATH" if os.name == "nt" else "Path"
    ]


def test_parent_discovery_stops_at_nearest_invalid_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "drift.toml").write_text("schema_version = 1\n", encoding="utf-8")
    nested = tmp_path / "nested"
    child = nested / "child"
    child.mkdir(parents=True)
    monkeypatch.chdir(child)
    assert resolve_project_root() == tmp_path.resolve()

    (nested / "drift.toml").write_text("broken", encoding="utf-8")
    root = resolve_project_root()

    assert root == nested.resolve()
    with pytest.raises(InvalidConfigError):
        load_config(root)
    assert resolve_project_root(search_parents=False) == child.resolve()
    assert resolve_project_root(Path("..")) == nested.resolve()


def test_explicit_root_does_not_search_parents(tmp_path: Path) -> None:
    (tmp_path / "drift.toml").touch()
    child = tmp_path / "child"
    child.mkdir()

    with pytest.raises(ProjectNotInitializedError):
        load_config(resolve_project_root(child))
    with pytest.raises(InvalidProjectError):
        resolve_project_root(child / "missing")
    with pytest.raises(InvalidProjectError):
        resolve_project_root(tmp_path / "drift.toml")
