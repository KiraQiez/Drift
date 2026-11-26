"""Render comparison results for a person reading the terminal."""

import json
import os

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from drift.comparison import Change, ChangeValue, Comparison
from drift.models import CollectorRecord, Observed, Snapshot
from drift.output import literal

_OUTCOMES = {
    "match": ("Match", "green"),
    "drift": ("Drift detected", "yellow"),
    "incomplete": ("Comparison incomplete", "yellow"),
}


def _count(amount: int, noun: str) -> str:
    return f"{amount} {noun}" + ("" if amount == 1 else "s")


def _label(value: ChangeValue) -> str:
    if value is None:
        return "(absent)"
    return literal(value) if isinstance(value, str) else json.dumps(value)


def _change_row(change: Change, details: bool) -> tuple[str, str, str, str]:
    before, after = _label(change.before), _label(change.after)
    if change.collector == "dependency":
        item = literal(change.probe.removeprefix("manifest:"))
        if not details:
            before = f"{before[:12]}…" if change.before is not None else before
            after = f"{after[:12]}…" if change.after is not None else after
    else:
        item = f"{change.collector}.{literal(change.probe)}"
    if change.subject is not None:
        item += f" [{literal(change.subject)}]"
    return change.kind.capitalize(), item, before, after


def _git_line(label: str, context: CollectorRecord) -> str:
    values = [
        f"{probe}={_label(result.value)}"
        for probe in ("branch", "commit", "worktree")
        if isinstance(result := context.probes.get(probe), Observed)
        and isinstance(result.value, str)
    ]
    suffix = f" · {', '.join(values)}" if values else ""
    return f"Git {label} ({context.status}){suffix}"


def render_comparison(
    result: Comparison,
    reference: Snapshot,
    before_git: CollectorRecord,
    after_git: CollectorRecord,
    *,
    details: bool,
) -> None:
    stream = typer.get_text_stream("stdout")
    console = Console(file=stream, force_terminal=stream.isatty())
    rich = (
        console.is_terminal
        and not console.is_dumb_terminal
        and "NO_COLOR" not in os.environ
        and console.width >= 72
    )
    outcome, color = _OUTCOMES[result.outcome]
    heading = f"{outcome} · {_count(len(result.changes), 'change')} · {_count(len(result.gaps), 'coverage gap')}"
    reference_line = f"Reference {reference.id}"
    if reference.message is not None:
        reference_line += f" · {literal(reference.message)}"

    if rich:
        console.print(
            Text(heading, style=f"bold {color}"), Text(reference_line), sep="\n"
        )
    else:
        typer.echo(f"{heading}\n{reference_line}")

    rows = [_change_row(change, details) for change in result.changes]
    if rich and rows:
        table = Table("Change", "Item", "Before", "Now", box=None, pad_edge=False)
        for row in rows:
            table.add_row(*(Text(value, overflow="fold") for value in row))
        console.print(table)
    else:
        for kind, item, before, after in rows:
            typer.echo(f"{kind}  {item}  {before} → {after}")

    for gap in result.gaps:
        probe = f".{literal(gap.probe)}" if gap.probe is not None else ""
        typer.echo(
            f"Coverage gap  {gap.collector}{probe}  {gap.side}: {gap.code.replace('_', ' ')}"
        )
    if result.warnings:
        typer.echo("No comparable environment observations.")
    if details:
        typer.echo(_git_line("reference", before_git))
        typer.echo(_git_line("current", after_git))
