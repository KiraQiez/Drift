"""Drift's command-line entry point."""

import json
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, cast

import typer

from drift.baseline import baseline_snapshot, set_baseline
from drift.live_comparison import compare_live
from drift.models import Snapshot, is_snapshot_reference, valid_message
from drift.output import Report, emit, literal
from drift.project import initialize, initialized_project
from drift.snapshots import capture_snapshot, latest_snapshot, list_history, summary
from drift.storage import resolve_snapshot

app = typer.Typer(name="drift", add_completion=False)
baseline = typer.Typer(name="baseline", add_completion=False)
app.add_typer(baseline)
JsonOption = Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")]


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    project: Annotated[
        Path | None, typer.Option("--project", help="Select the project directory.")
    ] = None,
    show_version: Annotated[
        bool, typer.Option("--version", help="Show the Drift version and exit.")
    ] = False,
) -> None:
    """Track changes in your development environment."""
    if show_version:
        typer.echo(f"drift {version('drift-dev-env')}")
        raise typer.Exit()

    ctx.obj = project
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command()
def init(ctx: typer.Context, as_json: JsonOption = False) -> None:
    """Initialize Drift in this project."""

    def run() -> Report:
        created = initialize(cast(Path | None, ctx.obj))
        return Report(
            {"created": created},
            "Initialized Drift project state."
            if created
            else "Drift project state is already initialized.",
        )

    emit("init", as_json, run)


@app.command()
def snapshot(
    ctx: typer.Context,
    message: Annotated[
        str | None, typer.Option("--message", "-m", help="Label this snapshot.")
    ] = None,
    as_json: JsonOption = False,
) -> None:
    """Capture the current environment."""
    if message is not None and not valid_message(message):
        raise typer.BadParameter(
            "Use 1–256 characters without control characters.", param_hint="--message"
        )

    def run() -> Report:
        root, config = initialized_project(cast(Path | None, ctx.obj))
        saved = capture_snapshot(root, config, message)
        note = f" · {literal(saved.message)}" if saved.message is not None else ""
        statuses = ", ".join(
            f"{name} {result.status}" for name, result in saved.collectors.items()
        )
        return Report(
            {"snapshot": summary(saved)},
            f"Saved snapshot {saved.id} · {saved.created_at}{note}\n{statuses}",
        )

    emit("snapshot", as_json, run)


def _validate_reference(reference: str) -> None:
    if not is_snapshot_reference(reference):
        raise typer.BadParameter(
            "Use a canonical snapshot ID or a lowercase hex prefix of at least six characters.",
            param_hint="SNAPSHOT",
        )


def _snapshot_line(record: Snapshot) -> str:
    note = f" · {literal(record.message)}" if record.message is not None else ""
    return f"{record.id} · {record.created_at}{note}"


@app.command()
def history(ctx: typer.Context, as_json: JsonOption = False) -> None:
    """List saved snapshots from oldest to newest."""

    def run() -> Report:
        root, _ = initialized_project(cast(Path | None, ctx.obj))
        entries = list_history(root)
        lines = [_snapshot_line(record) for record in entries.snapshots]
        lines.extend(
            f"Damaged snapshot {item['id']} ({item['code']})"
            for item in entries.damaged
        )
        return Report(
            {
                "snapshots": [summary(record) for record in entries.snapshots],
                "damaged": entries.damaged,
            },
            "\n".join(lines) or "No snapshots yet.",
            4 if entries.damaged else 0,
        )

    emit("history", as_json, run)


@app.command()
def show(ctx: typer.Context, snapshot: str, as_json: JsonOption = False) -> None:
    """Show a snapshot and its collector observations."""
    _validate_reference(snapshot)

    def run() -> Report:
        root, _ = initialized_project(cast(Path | None, ctx.obj))
        record = resolve_snapshot(root, snapshot)
        lines = [
            f"Snapshot {_snapshot_line(record)}",
            f"Schema version {record.schema_version}",
        ]
        lines.extend(
            f"Scope {name} = {json.dumps(value)}"
            for name, value in record.scope.model_dump().items()
        )
        for collector, result in record.collectors.items():
            lines.append(f"{collector} ({result.status})")
            for probe, observation in result.probes.items():
                detail = observation.model_dump()
                status = detail.pop("status")
                description = (
                    json.dumps(detail["value"]) if "value" in detail else detail["code"]
                )
                lines.append(f"  {literal(probe)} ({status}) {description}")
        return Report({"snapshot": record.model_dump()}, "\n".join(lines))

    emit("show", as_json, run)


@app.command()
def diff(
    ctx: typer.Context,
    snapshot: Annotated[
        str | None, typer.Argument(help="Snapshot ID or unique prefix.")
    ] = None,
    as_json: JsonOption = False,
) -> None:
    """Compare the live environment with a saved snapshot."""
    if snapshot is not None:
        _validate_reference(snapshot)

    def run() -> Report:
        root, config = initialized_project(cast(Path | None, ctx.obj))
        reference = (
            latest_snapshot(root)
            if snapshot is None
            else resolve_snapshot(root, snapshot)
        )
        return compare_live(root, config, reference)

    emit("diff", as_json, run)


@baseline.callback(invoke_without_command=True)
def _baseline(ctx: typer.Context) -> None:
    """Manage the known-working baseline."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@baseline.command("set")
def baseline_set(
    ctx: typer.Context, snapshot: str, as_json: JsonOption = False
) -> None:
    """Make a saved snapshot the baseline."""
    _validate_reference(snapshot)

    def run() -> Report:
        root, _ = initialized_project(cast(Path | None, ctx.obj))
        snapshot_id = set_baseline(root, snapshot)
        return Report({"baseline_id": snapshot_id}, f"Baseline set to {snapshot_id}")

    emit("baseline set", as_json, run)


@app.command()
def verify(ctx: typer.Context, as_json: JsonOption = False) -> None:
    """Verify the live environment against the known-working baseline."""

    def run() -> Report:
        root, config = initialized_project(cast(Path | None, ctx.obj))
        return compare_live(root, config, baseline_snapshot(root))

    emit("verify", as_json, run)
