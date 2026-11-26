"""Typed observations shared by collectors and the scheduler."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Literal

from drift.config import ProjectConfig

type CollectorId = Literal[
    "dependency", "docker", "environment", "git", "runtime", "system"
]
type CollectorStatus = Literal[
    "ok", "partial", "unavailable", "unsupported", "failed", "disabled"
]
type ProbeValue = bool | str | list[str] | dict[str, dict[str, int]]
type DiagnosticCode = Literal[
    "executable_missing",
    "not_found",
    "permission_denied",
    "timeout",
    "output_limit",
    "size_limit",
    "unsafe_path",
    "unsupported_platform",
    "unsupported_launcher",
    "unsupported_checkout",
    "invalid_output",
    "invalid_input",
    "io_error",
    "command_failed",
    "collector_error",
    "input_changed",
    "daemon_unreachable",
    "prerequisite_missing",
    "not_configured",
    "detached_head",
    "unborn_head",
]

COLLECTOR_IDS: tuple[CollectorId, ...] = (
    "dependency",
    "docker",
    "environment",
    "git",
    "runtime",
    "system",
)


@dataclass(frozen=True)
class Observation:
    value: ProbeValue
    status: Literal["ok"] = field(default="ok", init=False)


@dataclass(frozen=True)
class ProbeIssue:
    status: Literal["unavailable", "unsupported", "failed", "not_applicable"]
    code: DiagnosticCode


type ProbeResult = Observation | ProbeIssue


def known_absence(collector: CollectorId, code: DiagnosticCode) -> bool:
    return (collector, code) in {
        ("runtime", "executable_missing"),
        ("dependency", "not_found"),
    }


@dataclass(frozen=True)
class CollectorResult:
    status: CollectorStatus
    probes: dict[str, ProbeResult]


@dataclass(frozen=True)
class CollectorContext:
    root: Path
    config: ProjectConfig
    deadline: float

    def remaining(self) -> float:
        """Return the time available for additional work."""
        return max(0.0, self.deadline - monotonic())


@dataclass(frozen=True)
class CollectorSpec:
    probe_ids: tuple[str, ...]
    collect: Callable[[CollectorContext], Mapping[str, ProbeResult]]

    def __post_init__(self) -> None:
        if not self.probe_ids or len(set(self.probe_ids)) != len(self.probe_ids):
            raise ValueError(
                "A collector must declare a nonempty set of unique probe IDs."
            )
