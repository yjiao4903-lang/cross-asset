"""Current-main CLI commands (part A)."""

from __future__ import annotations

import json

import typer

from cross_asset.cli import app
from cross_asset.cli_helpers import not_implemented
from cross_asset.logging import configure_logging
from cross_asset.settings import get_settings


@app.command("validate-data-file")
def validate_data_file(file: str = typer.Argument(...), manifest: str | None = typer.Option(None, "--manifest"), output: str | None = typer.Option(None, "--output")):
    from .ingestion.acceptance import exit_code
    from .ingestion.acceptance import validate_data_file as validate
    result = validate(file, manifest)
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
    if output:
        from pathlib import Path
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)
    raise typer.Exit(exit_code(result))
