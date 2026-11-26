"""Capture and report a live comparison without modifying project state."""

from dataclasses import asdict
from functools import partial
from pathlib import Path

from drift.comparison import compare
from drift.comparison_output import render_comparison
from drift.config import ProjectConfig
from drift.models import Snapshot
from drift.output import Report
from drift.snapshots import capture


def compare_live(
    root: Path, config: ProjectConfig, reference: Snapshot, *, details: bool
) -> Report:
    current = capture(root, config)
    result = compare(reference, current)
    before_git, after_git = reference.collectors["git"], current.collectors["git"]
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
        partial(
            render_comparison, result, reference, before_git, after_git, details=details
        ),
        result.exit_code,
    )
