"""Project discovery and validation of the v1 TOML configuration."""

import os
import tomllib
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from drift.exceptions import (
    InvalidConfigError,
    InvalidProjectError,
    ProjectNotInitializedError,
    UnsupportedSchemaError,
)
from drift.paths import open_project_file, project_path_parts

CONFIG_NAME = "drift.toml"


class _Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class CollectorSettings(_Settings):
    system: bool = True
    runtime: bool = True
    docker: bool = True
    environment: bool = True
    dependency: bool = True
    git: bool = True


class EnvironmentSettings(_Settings):
    files: list[str] = Field(default_factory=list)
    active_allowlist: list[str] | None = None

    @field_validator("files")
    @classmethod
    def _validate_files(cls, files: list[str]) -> list[str]:
        for path in files:
            project_path_parts(path)
        if len({os.path.normcase(path) for path in files}) != len(files):
            raise ValueError("Configured environment files must be unique.")
        return files

    @field_validator("active_allowlist")
    @classmethod
    def _validate_allowlist(cls, names: list[str] | None) -> list[str] | None:
        if names is None:
            return None
        if any(not name or "\0" in name or "=" in name for name in names):
            raise ValueError("The active allowlist must contain valid variable names.")
        normalized = [name.upper() for name in names] if os.name == "nt" else names
        if len(set(normalized)) != len(names):
            raise ValueError("Active environment variable names must be unique.")
        return normalized


class DockerSettings(_Settings):
    compose_project: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")] | None = (
        None
    )


class ProjectConfig(_Settings):
    schema_version: int = Field(ge=1, le=1)
    collectors: CollectorSettings = Field(default_factory=CollectorSettings)
    environment: EnvironmentSettings = Field(default_factory=EnvironmentSettings)
    docker: DockerSettings = Field(default_factory=DockerSettings)


def resolve_project_root(
    project: Path | None = None, *, search_parents: bool = True
) -> Path:
    """Select an explicit directory or discover the nearest configuration."""
    try:
        start = (Path.cwd() if project is None else project).resolve(strict=True)
        if not start.is_dir():
            raise InvalidProjectError("Select an existing project directory.")
    except (OSError, RuntimeError, ValueError):
        raise InvalidProjectError("Select an existing project directory.") from None

    if project is not None or not search_parents:
        return start

    for directory in (start, *start.parents):
        try:
            (directory / CONFIG_NAME).lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise InvalidConfigError("Could not access drift.toml.") from None
        return directory
    raise ProjectNotInitializedError("No drift.toml was found. Run drift init first.")


def load_config(root: Path) -> ProjectConfig:
    """Read and validate configuration without accessing configured inputs."""
    try:
        with open_project_file(root, CONFIG_NAME) as stream:
            settings = tomllib.load(stream)
    except FileNotFoundError:
        raise ProjectNotInitializedError(
            "No drift.toml was found. Run drift init first."
        ) from None
    except (OSError, ValueError, RecursionError):
        raise InvalidConfigError("Could not read drift.toml as valid TOML.") from None

    schema_version = settings.get("schema_version")
    if type(schema_version) is int and schema_version != 1:
        raise UnsupportedSchemaError("The drift.toml schema version is unsupported.")
    try:
        return ProjectConfig.model_validate(settings)
    except ValidationError:
        raise InvalidConfigError(
            "drift.toml settings do not match the v1 schema."
        ) from None
