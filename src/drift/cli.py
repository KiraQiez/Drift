"""Drift's command-line entry point."""

from importlib.metadata import version
from typing import Annotated

import typer

app = typer.Typer(name="drift", add_completion=False)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    show_version: Annotated[
        bool, typer.Option("--version", help="Show the Drift version and exit.")
    ] = False,
) -> None:
    """Track changes in your development environment."""
    if show_version:
        typer.echo(f"drift {version('drift-dev-env')}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
