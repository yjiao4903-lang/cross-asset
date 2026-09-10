"""Shared helpers for current-main CLI command modules."""

from __future__ import annotations

import typer


def not_implemented(command: str) -> None:
    typer.echo(f"{command}: interface reserved; implementation is not installed yet.")


def as_naive_utc(value):
    """Normalize a timestamp cell from DuckDB/pandas to naive UTC datetime."""
    import pandas as pd

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.to_pydatetime()


def reserved(name: str):
    def command() -> None:
        not_implemented(name)

    command.__name__ = name.replace("-", "_")
    return command
