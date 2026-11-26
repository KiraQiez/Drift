"""Drift's command-line entry point."""

from importlib.metadata import version
from pathlib import Path
from typing import Annotated, cast

import typer

from drift.output import Report, emit
from drift.project import initialize

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
