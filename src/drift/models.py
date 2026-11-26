"""Validated version-one snapshot records."""

import re
import unicodedata
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from drift.collectors import dependency, docker, git, runtime, system
from drift.collectors.base import (
    COLLECTOR_IDS,
    CollectorId,
    CollectorStatus,
    DiagnosticCode,
    Observation,
    ProbeIssue,
    ProbeValue,
)
from drift.collectors.engine import collector_status
from drift.paths import project_path_parts

_ID_PATTERN = r"^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$"
_ID = re.compile(_ID_PATTERN)
_PREFIX = re.compile(r"[0-9a-f]{6,32}")
_UTC = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z"
)
_CHECKSUM = re.compile(r"[0-9a-f]{64}")
_DECLARED_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SERVICE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_STATES = {"created", "running", "paused", "restarting", "removing", "exited", "dead"}
_FIXED_PROBES = {
    "dependency": dependency.PROBE_IDS,
    "docker": docker.PROBE_IDS,
    "git": git.PROBE_IDS,
    "runtime": runtime.PROBE_IDS,
    "system": system.PROBE_IDS,
}
_BOOLEAN_PROBES = {
    ("docker", "installed"),
    ("docker", "compose_installed"),
    ("docker", "daemon_reachable"),
    ("git", "repository"),
}

type SnapshotId = Annotated[str, Field(pattern=_ID_PATTERN)]


def is_snapshot_id(value: str) -> bool:
    return _ID.fullmatch(value) is not None


def is_snapshot_reference(value: str) -> bool:
    return _PREFIX.fullmatch(value) is not None and (
        len(value) < 32 or is_snapshot_id(value)
    )


def valid_message(value: str) -> bool:
    return 1 <= len(value) <= 256 and not any(
        unicodedata.category(character) in {"Cc", "Cs"} for character in value
    )


def _valid_names(names: list[str], *, declared: bool = False) -> bool:
    return names == sorted(set(names)) and all(
        name
        and "=" not in name
        and "\0" not in name
        and (not declared or _DECLARED_NAME.fullmatch(name))
        for name in names
    )


class StrictRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)


class Observed(StrictRecord):
    status: Literal["ok"]
    value: ProbeValue


class Issue(StrictRecord):
    status: Literal["unavailable", "unsupported", "failed", "not_applicable"]
    code: DiagnosticCode


type ProbeRecord = Annotated[Observed | Issue, Field(discriminator="status")]


class CollectorRecord(StrictRecord):
    status: CollectorStatus
    probes: dict[str, ProbeRecord]


class Scope(StrictRecord):
    active_allowlist: list[str] | None
    active_name_case: Literal["preserve", "uppercase"]
    compose_project: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")] | None

    @model_validator(mode="after")
    def _check_allowlist(self) -> Self:
        if self.active_allowlist is not None and (
            not _valid_names(self.active_allowlist)
            or (
                self.active_name_case == "uppercase"
                and any(name != name.upper() for name in self.active_allowlist)
            )
        ):
            raise ValueError("Invalid active name scope.")
        return self


def _valid_value(
    collector: CollectorId, probe: str, value: ProbeValue, scope: Scope
) -> bool:
    if (collector, probe) in _BOOLEAN_PROBES:
        return isinstance(value, bool)
    if collector == "environment":
        if not isinstance(value, list) or not _valid_names(
            value, declared=probe != "active"
        ):
            return False
        if probe != "active":
            return True
        if scope.active_name_case == "uppercase" and any(
            name != name.upper() for name in value
        ):
            return False
        return scope.active_allowlist is None or set(value) <= set(
            scope.active_allowlist
        )
    if collector == "docker" and probe == "services":
        return (
            scope.compose_project is not None
            and isinstance(value, dict)
            and all(
                _SERVICE.fullmatch(service)
                and counts
                and set(counts) <= _STATES
                and all(count > 0 for count in counts.values())
                for service, counts in value.items()
            )
        )
    if not isinstance(value, str) or not value:
        return False
    if collector == "dependency":
        return _CHECKSUM.fullmatch(value) is not None
    if collector == "git" and probe == "commit":
        return len(value) in {40, 64} and all(
            character in "0123456789abcdef" for character in value
        )
    if collector == "git" and probe == "worktree":
        return value in {"clean", "dirty"}
    return True


class CapturedEnvironment(StrictRecord):
    scope: Scope
    collectors: dict[CollectorId, CollectorRecord]

    @model_validator(mode="after")
    def _check_collectors(self) -> Self:
        if self.collectors.keys() != set(COLLECTOR_IDS):
            raise ValueError("Invalid collector set.")
        for key, record in self.collectors.items():
            probes = record.probes
            if record.status == "disabled" and not probes:
                continue
            if key == "environment":
                files = set(probes) - {"active"}
                if "active" not in probes or any(
                    not item.startswith("file:") for item in files
                ):
                    raise ValueError("Invalid environment probe set.")
                for item in files:
                    project_path_parts(item.removeprefix("file:"))
                if self.scope.active_name_case == "uppercase" and len(
                    {item.upper() for item in files}
                ) != len(files):
                    raise ValueError("Duplicate environment probe paths.")
            elif probes.keys() != set(_FIXED_PROBES[key]):
                raise ValueError("Invalid collector probe set.")
            for probe, result in probes.items():
                if isinstance(result, Observed) and not _valid_value(
                    key, probe, result.value, self.scope
                ):
                    raise ValueError("Invalid probe value.")
            if (
                collector_status(
                    key,
                    {
                        probe: Observation(result.value)
                        if isinstance(result, Observed)
                        else ProbeIssue(result.status, result.code)
                        for probe, result in probes.items()
                    },
                )
                != record.status
            ):
                raise ValueError("Invalid aggregate collector status.")
        return self


class Snapshot(CapturedEnvironment):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    id: SnapshotId
    created_at: str
    message: str | None

    @field_validator("created_at")
    @classmethod
    def _check_timestamp(cls, value: str) -> str:
        if not _UTC.fullmatch(value):
            raise ValueError("Expected a UTC timestamp.")
        datetime.fromisoformat(value)
        return value

    @field_validator("message")
    @classmethod
    def _check_message(cls, value: str | None) -> str | None:
        if value is not None and not valid_message(value):
            raise ValueError("Invalid snapshot message.")
        return value


class Metadata(StrictRecord):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    baseline_id: SnapshotId | None
