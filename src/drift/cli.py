"""Drift's command-line entry point."""

from importlib.metadata import version
from pathlib import Path
from typing import Annotated, cast

import typer

from drift.models import valid_message
from drift.output import Report, emit, literal
from drift.project import initialize, initialized_project
from drift.snapshots import capture_snapshot, summary

app = typer.Typer(name="drift", add_completion=False)
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
