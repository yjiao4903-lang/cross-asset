"""Standalone C0 staging CLI. Does not modify src/cross_asset/cli.py."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .treasury_nyfed_c0_contract import DEFAULT_REGISTRY_PATH, require_c0_only
from .treasury_nyfed_registry import load_registry
from .treasury_nyfed_staging import collect_all, research_transforms

app = typer.Typer(add_completion=False, help="C67 Treasury/NY Fed C0 research staging")


@app.command("contract")
def contract_command() -> None:
    typer.echo(json.dumps(require_c0_only(), sort_keys=True))


@app.command("list-datasets")
def list_datasets(registry: str = typer.Option(DEFAULT_REGISTRY_PATH, "--registry")) -> None:
    loaded = load_registry(registry)
    payload = [
        {
            "dataset_id": item.dataset_id,
            "provider": item.provider,
            "status": item.status,
            "endpoint": item.endpoint,
        }
        for item in loaded.datasets
    ]
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command("collect")
def collect_command(
    dataset: str | None = typer.Option(None, "--dataset"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    registry: str = typer.Option(DEFAULT_REGISTRY_PATH, "--registry"),
    cache_dir: str | None = typer.Option(None, "--cache-dir"),
    output: str | None = typer.Option(None, "--output"),
    live: bool = typer.Option(False, "--live"),
) -> None:
    manifest = collect_all(
        registry_path=registry,
        start=start,
        end=end,
        dataset_id=dataset,
        cache_dir=cache_dir,
        output=output,
        live=live,
    )
    typer.echo(json.dumps(manifest, indent=2, sort_keys=True, default=str))


@app.command("transforms")
def transforms_command(
    input_json: str = typer.Argument(...),
    decision_time: str = typer.Option(..., "--decision-time"),
) -> None:
    payload = json.loads(Path(input_json).read_text(encoding="utf-8"))
    result = research_transforms(payload, decision_time)
    typer.echo(json.dumps(result, indent=2, sort_keys=True, default=str))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
