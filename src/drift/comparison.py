"""Deterministic comparison of two validated environment captures."""

from dataclasses import dataclass
from typing import Literal

from drift.collectors.base import (
    COLLECTOR_IDS,
    CollectorId,
    DiagnosticCode,
    ProbeValue,
    known_absence,
)
from drift.models import CapturedEnvironment, Issue, Observed, ProbeRecord, Scope

type ChangeValue = bool | str | dict[str, int] | None
type Side = Literal["reference", "current", "both"]
type GapCode = DiagnosticCode | Literal["scope_changed"]

_DOCKER_PREREQUISITES = {
    "client_version": ("installed",),
    "compose_installed": ("installed",),
    "compose_version": ("installed", "compose_installed"),
    "daemon_reachable": ("installed",),
}


@dataclass(frozen=True)
class Change:
    collector: CollectorId
    probe: str
    subject: str | None
    kind: Literal["added", "removed", "modified"]
    before: ChangeValue
    after: ChangeValue


@dataclass(frozen=True)
class Gap:
    collector: CollectorId
    probe: str | None
    side: Side
    code: GapCode


@dataclass(frozen=True)
class Comparison:
    changes: list[Change]
    gaps: list[Gap]
    comparable: int

    @property
    def warnings(self) -> list[str]:
        return [] if self.comparable else ["no_comparable_observations"]

    @property
    def outcome(self) -> Literal["match", "drift", "incomplete"]:
        if self.changes:
            return "drift"
        return "incomplete" if self.gaps or self.warnings else "match"

    @property
    def exit_code(self) -> Literal[0, 3, 4]:
        if self.outcome == "drift":
            return 3
        return 4 if self.outcome == "incomplete" else 0


def _change(
    collector: CollectorId,
    probe: str,
    subject: str | None,
    before: ChangeValue,
    after: ChangeValue,
) -> Change:
    kind: Literal["added", "removed", "modified"]
    kind = "added" if before is None else "removed" if after is None else "modified"
    return Change(collector, probe, subject, kind, before, after)


def _members(value: ProbeValue | None) -> dict[str, ChangeValue]:
    if isinstance(value, list):
        return dict.fromkeys(value, True)
    if isinstance(value, dict):
        return dict(value)
    return {}


def _changes(
    collector: CollectorId, probe: str, old: ProbeRecord, new: ProbeRecord
) -> list[Change]:
    before = old.value if isinstance(old, Observed) else None
    after = new.value if isinstance(new, Observed) else None
    if before == after:
        return []
    if isinstance(before, (list, dict)) or isinstance(after, (list, dict)):
        original, current = _members(before), _members(after)
        return [
            _change(collector, probe, name, original.get(name), current.get(name))
            for name in sorted(original.keys() | current.keys())
            if original.get(name) != current.get(name)
        ]
    return [_change(collector, probe, None, before, after)]


def _scope_changed(collector: CollectorId, probe: str, old: Scope, new: Scope) -> bool:
    if collector == "environment" and probe == "active":
        return (
            old.active_allowlist != new.active_allowlist
            or old.active_name_case != new.active_name_case
        )
    return (
        collector == "docker"
        and probe == "services"
        and old.compose_project != new.compose_project
    )


def _issue_code(collector: CollectorId, result: ProbeRecord) -> DiagnosticCode | None:
    if isinstance(result, Observed):
        return None
    if result.status == "unavailable" and known_absence(collector, result.code):
        return None
    return result.code


def _explained(
    probe: str,
    issue: ProbeRecord,
    absent: dict[str, ProbeRecord],
    present: dict[str, ProbeRecord],
) -> bool:
    if (
        not isinstance(issue, Issue)
        or issue.status != "not_applicable"
        or issue.code != "prerequisite_missing"
    ):
        return False
    return any(
        absent.get(key) == Observed(status="ok", value=False)
        and present.get(key) == Observed(status="ok", value=True)
        for key in _DOCKER_PREREQUISITES.get(probe, ())
    )


def compare(reference: CapturedEnvironment, current: CapturedEnvironment) -> Comparison:
    changes: list[Change] = []
    gaps: list[Gap] = []
    comparable = 0
    for collector in COLLECTOR_IDS:
        if collector == "git":
            continue
        old, new = reference.collectors[collector], current.collectors[collector]
        if old.status == "disabled" or new.status == "disabled":
            if old.status != new.status:
                gaps.append(
                    Gap(
                        collector,
                        None,
                        "reference" if old.status == "disabled" else "current",
                        "scope_changed",
                    )
                )
            continue
        for probe in sorted(old.probes.keys() | new.probes.keys()):
            if _scope_changed(collector, probe, reference.scope, current.scope):
                gaps.append(Gap(collector, probe, "both", "scope_changed"))
                continue
            if probe not in old.probes or probe not in new.probes:
                gaps.append(
                    Gap(
                        collector,
                        probe,
                        "reference" if probe not in old.probes else "current",
                        "scope_changed",
                    )
                )
                continue
            before, after = old.probes[probe], new.probes[probe]
            services = collector == "docker" and probe == "services"
            if services and reference.scope.compose_project is None:
                continue
            if not services and before.status == after.status == "not_applicable":
                continue
            left, right = _issue_code(collector, before), _issue_code(collector, after)
            if left is None and right is None:
                comparable += 1
                changes.extend(_changes(collector, probe, before, after))
                continue
            if collector == "docker":
                if _explained(probe, before, old.probes, new.probes):
                    left = None
                if _explained(probe, after, new.probes, old.probes):
                    right = None
            if left is not None and left == right:
                gaps.append(Gap(collector, probe, "both", left))
            else:
                if left is not None:
                    gaps.append(Gap(collector, probe, "reference", left))
                if right is not None:
                    gaps.append(Gap(collector, probe, "current", right))
    return Comparison(
        changes,
        sorted(
            gaps, key=lambda gap: (gap.collector, gap.probe or "", gap.side, gap.code)
        ),
        comparable,
    )
