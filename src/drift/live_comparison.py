"""Capture and report a live comparison without modifying project state."""

import json
from dataclasses import asdict
from pathlib import Path

from drift.comparison import ChangeValue, compare
from drift.config import ProjectConfig
from drift.models import CollectorRecord, Observed, Snapshot
from drift.output import Report, literal
from drift.snapshots import capture


def _label(value: ChangeValue) -> str:
    if value is None:
        return "(absent)"
    return literal(value) if isinstance(value, str) else json.dumps(value)


def _git_line(label: str, context: CollectorRecord) -> str:
    values = [
        f"{probe}={_label(result.value)}"
        for probe in ("branch", "commit", "worktree")
        if isinstance(result := context.probes.get(probe), Observed)
        and isinstance(result.value, str)
    ]
    return f"Git {label} ({context.status})" + (
        f" · {', '.join(values)}" if values else ""
    )


def compare_live(root: Path, config: ProjectConfig, reference: Snapshot) -> Report:
    current = capture(root, config)
    result = compare(reference, current)
    heading = {
        "match": "Environment matches",
        "drift": "Drift detected against",
        "incomplete": "Comparison incomplete against",
    }[result.outcome]
    lines = [f"{heading} {reference.id}"]
    for change in result.changes:
        subject = f" [{literal(change.subject)}]" if change.subject is not None else ""
        lines.append(
            f"{change.kind.capitalize()}  {change.collector}.{literal(change.probe)}{subject}"
            f"  {_label(change.before)} → {_label(change.after)}"
        )
    for gap in result.gaps:
        probe = f".{literal(gap.probe)}" if gap.probe is not None else ""
        lines.append(f"Coverage gap  {gap.collector}{probe}  {gap.side}: {gap.code}")
    if result.warnings:
        lines.append("No comparable environment observations.")
    before_git, after_git = reference.collectors["git"], current.collectors["git"]
    lines.extend((_git_line("reference", before_git), _git_line("current", after_git)))
    return Report(
        {
            "reference_id": reference.id,
            "outcome": result.outcome,
            "changes": [asdict(change) for change in result.changes],
            "gaps": [asdict(gap) for gap in result.gaps],
            "warnings": result.warnings,
            "git": {
                "reference": before_git.model_dump(),
                "current": after_git.model_dump(),
            },
        },
        "\n".join(lines),
        result.exit_code,
    )
