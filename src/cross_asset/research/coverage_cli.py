"""Standalone diagnostic CLI for component coverage and G0 registry."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .component_coverage import snapshot_from_wiring
from .factor_registry import audit_factor_registry

app = typer.Typer(
    name="component-coverage",
    help="P0 missing-component diagnostics. Never writes allocation.",
)


def _emit(payload: object) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True, indent=2))


@app.command("snapshot")
def snapshot_command(
    allocation: str = typer.Option("config/allocation.yml", "--allocation"),
    policy: str = typer.Option("config/component_coverage.yml", "--policy"),
    personal: bool = typer.Option(False, "--personal"),
    output: str | None = typer.Option(None, "--output"),
) -> None:
    report = snapshot_from_wiring(
        allocation_path=allocation,
        policy_path=policy,
        personal=personal,
    )
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, default=str, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    _emit(report)


@app.command("registry")
def registry_command(
    registry: str = typer.Option("config/factor_registry.yml", "--registry"),
) -> None:
    audit = audit_factor_registry(registry)
    _emit(audit.to_dict())
    if audit.status != "G0_READY":
        raise typer.Exit(2)


if __name__ == "__main__":
    app()
