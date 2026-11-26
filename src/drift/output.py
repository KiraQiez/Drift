"""Shared CLI reports and stream handling."""

import json
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

import typer

from drift.exceptions import DriftError


@dataclass(frozen=True)
class Report:
    result: dict[str, object]
    text: str
    exit_code: int = 0


def literal(value: str) -> str:
    return "".join(
        ascii(character)[1:-1]
        if unicodedata.category(character) in {"Cc", "Cf", "Cs"}
        else character
        for character in value
    )


def _json(command: str, key: str, value: dict[str, object]) -> None:
    typer.echo(json.dumps({"schema_version": 1, "command": command, key: value}))


def emit(command: str, as_json: bool, operation: Callable[[], Report]) -> None:
    try:
        report = operation()
    except DriftError as error:
        if as_json:
            _json(command, "error", {"code": error.code, "message": str(error)})
        else:
            typer.echo(f"{error.code}: {literal(str(error))}", err=True)
        raise typer.Exit(1) from None
    except Exception:
        message = "An unexpected error prevented Drift from completing the command."
        if as_json:
            _json(command, "error", {"code": "internal_error", "message": message})
        else:
            typer.echo(f"internal_error: {message}", err=True)
        raise typer.Exit(1) from None
    if as_json:
        _json(command, "result", report.result)
    else:
        typer.echo(report.text)
    if report.exit_code:
        raise typer.Exit(report.exit_code)
