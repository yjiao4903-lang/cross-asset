"""Isolated CLI for guarded research/OOS workflows.

Run with::

    python -m cross_asset.research.cli --help

This command surface is intentionally separate from the daily Cross/Marco CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import typer

from cross_asset.settings import get_settings
from cross_asset.storage import (
    ProvenanceStore,
    approved_observations_asof,
    code_version,
    config_hash,
    init_db,
)

from . import (
    build_research_plan,
    evaluate_research_readiness,
    execute_walk_forward,
    load_decision_dates,
    load_research_model_config,
    load_research_protocol,
    paired_oos_metrics,
    stitch_oos_path,
    verdict_from_thresholds,
)
from .execution_timing import (
    annotate_research_execution_timing,
    research_execution_timing_summary,
)
from .model_config import (
    load_research_asset_market_map,
    research_effective_config_paths,
)
from .storage import persist_fold_result, persist_research_plan

app = typer.Typer(
    name="cross-asset-research",
    help="Guarded real-data admission and OOS research workflows.",
)


def _database_path(database: str | None) -> str:
    return database or get_settings().database_path


def _emit(payload: object) -> None:
    typer.echo(
        json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
            sort_keys=True,
            indent=2,
        )
    )


@app.command("ingest")
def ingest_command(
    input_json: str = typer.Argument(...),
    database: str | None = typer.Option(None, "--database"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Validate and optionally admit research observations into the PIT store."""
    from cross_asset.ingestion.research import ingest_research_data

    payload = json.loads(Path(input_json).read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else payload
    policies = payload.get("policies", {}) if isinstance(payload, dict) else {}
    store = None if dry_run else init_db(_database_path(database))
    try:
        result = ingest_research_data(
            records,
            policies=policies,
            store=store,
            dry_run=dry_run,
        )
    finally:
        if store is not None:
            store.close()
    _emit(result)
    if result["status"] not in {"ADMISSIBLE", "ADMITTED"}:
        raise typer.Exit(1)


@app.command("readiness")
def readiness_command(
    database: str | None = typer.Option(None, "--database"),
    config: str = typer.Option("config/research.yml", "--config"),
    decision_dates: str | None = typer.Option(None, "--decision-dates"),
) -> None:
    """Evaluate whether admitted PIT data is ready for the frozen OOS protocol."""
    protocol = load_research_protocol(config)
    model_config = load_research_model_config()
    return_series = [
        spec.series_id
        for spec in model_config.return_specs.values()
        if spec.series_id is not None
    ]
    store = init_db(_database_path(database))
    try:
        dates = load_decision_dates(decision_dates) if decision_dates else None
        result = evaluate_research_readiness(
            store.conn,
            protocol,
            required_series=return_series,
            decision_times=dates,
        )
    finally:
        store.close()
    _emit(result)
    if result["status"] != "READY_FOR_OOS":
        raise typer.Exit(2)


@app.command("plan")
def plan_command(
    decision_dates: str = typer.Argument(...),
    config: str = typer.Option("config/research.yml", "--config"),
    output: str = typer.Option("artifacts/research/research_plan.json", "--output"),
    database: str | None = typer.Option(None, "--database"),
) -> None:
    """Build and persist the sealed research plan without releasing holdout data."""
    protocol = load_research_protocol(config)
    plan = build_research_plan(load_decision_dates(decision_dates), protocol)
    payload = plan.to_dict()
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
    )
    effective_config_hash = config_hash(research_effective_config_paths(config))
    store = init_db(_database_path(database))
    try:
        persisted = persist_research_plan(
            store,
            plan=payload,
            config_hash=effective_config_hash,
            code_version=code_version("."),
        )
    finally:
        store.close()
    result = {**payload, **persisted, "config_hash": effective_config_hash}
    _emit(result)
    if plan.status != "READY_FOR_OOS":
        raise typer.Exit(2)


@app.command("run-oos")
def run_oos_command(
    decision_dates: str = typer.Argument(...),
    database: str | None = typer.Option(None, "--database"),
    config: str = typer.Option("config/research.yml", "--config"),
    output: str = typer.Option("artifacts/research/oos", "--output"),
) -> None:
    """Run only the frozen development walk-forward sample; holdout stays sealed."""
    protocol = load_research_protocol(config)
    dates = load_decision_dates(decision_dates)
    plan = build_research_plan(dates, protocol)
    store = init_db(_database_path(database))
    effective_config_hash = config_hash(research_effective_config_paths(config))
    try:
        model_config = load_research_model_config()
        return_series = [
            spec.series_id
            for spec in model_config.return_specs.values()
            if spec.series_id is not None
        ]
        development_dates = dates[: plan.development_count]
        readiness = evaluate_research_readiness(
            store.conn,
            protocol,
            required_series=return_series,
            decision_times=development_dates,
        )
        if readiness["status"] != "READY_FOR_OOS" or plan.status != "READY_FOR_OOS":
            _emit(
                {
                    "status": "BLOCKED",
                    "readiness": readiness,
                    "plan": plan.to_dict(),
                }
            )
            raise typer.Exit(2)

        # A formal run is only reproducible when both its admitted information set
        # and every effective consumed config participate in immutable provenance.
        snapshot_cutoff = pd.Timestamp(development_dates.max()).to_pydatetime()
        snapshot_rows = approved_observations_asof(
            store.conn,
            snapshot_cutoff,
            required_usage_status="RESEARCH_ADMISSIBLE",
            allowed_quality={"ok", "closed"},
        ).df()
        if snapshot_rows.empty:
            raise ValueError("research_data_snapshot_missing")
        snapshot_records = snapshot_rows.to_dict("records")
        snapshot_id = ProvenanceStore(store.conn).create_snapshot(
            snapshot_records,
            data_cutoff=snapshot_cutoff,
            config_hash_value=effective_config_hash,
        )

        fold_rows = execute_walk_forward(
            store.conn,
            decision_dates=dates,
            plan=plan.to_dict(),
            protocol=protocol,
            model_config=model_config,
        )
        asset_market_map = load_research_asset_market_map()
        fold_rows = annotate_research_execution_timing(
            fold_rows,
            model_config.return_specs,
            asset_market_map,
        )
        stitched = stitch_oos_path(
            fold_rows,
            plan.to_dict(),
            cost_bps=protocol.base_cost_bps,
            turnover_convention=protocol.turnover_convention,
            charge_initial_trade=protocol.charge_initial_trade,
        )
        stitched = annotate_research_execution_timing(
            stitched,
            model_config.return_specs,
            asset_market_map,
            terminal_group_columns=("benchmark",),
        )
        execution_timing = research_execution_timing_summary(stitched)
        pivot = stitched.pivot(
            index="decision_date",
            columns="benchmark",
            values="net_return",
        )
        if "FULL_MODEL" not in pivot or "STATIC" not in pivot:
            raise ValueError("full_model_and_static_oos_returns_required")
        metrics = paired_oos_metrics(pivot["FULL_MODEL"], pivot["STATIC"])
        verdict = verdict_from_thresholds(metrics, protocol.evaluation_thresholds)
        persisted = persist_research_plan(
            store,
            plan=plan.to_dict(),
            config_hash=effective_config_hash,
            code_version=code_version("."),
            data_snapshot_id=snapshot_id,
        )
        research_run_id = persisted["research_run_id"]
        for (fold, benchmark), group in fold_rows.groupby(["fold", "benchmark"]):
            valid = group["gross_return"].dropna().astype(float)
            persist_fold_result(
                store,
                research_run_id=research_run_id,
                fold=int(fold),
                benchmark=str(benchmark),
                metrics={
                    "observations": len(valid),
                    "mean_gross_return": float(valid.mean()) if len(valid) else None,
                },
                data_snapshot_id=snapshot_id,
                status="COMPLETE",
            )

        root = Path(output)
        root.mkdir(parents=True, exist_ok=True)

        def records(frame: pd.DataFrame) -> list[dict]:
            clean = frame.astype(object).where(pd.notna(frame), None)
            return clean.to_dict("records")

        artifacts = {
            "plan.json": plan.to_dict(),
            "fold_rows.json": records(fold_rows),
            "stitched_oos.json": records(stitched),
            "summary.json": {
                "status": "OOS_COMPLETE",
                "holdout_sealed": True,
                "protocol_hash": protocol.protocol_hash,
                "config_hash": effective_config_hash,
                "data_snapshot_id": snapshot_id,
                "research_run_id": research_run_id,
                "execution_timing": execution_timing,
                "metrics_vs_static": metrics,
                **verdict,
            },
        }
        for name, artifact in artifacts.items():
            (root / name).write_text(
                json.dumps(
                    artifact,
                    ensure_ascii=False,
                    default=str,
                    sort_keys=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        _emit(artifacts["summary.json"])
    finally:
        store.close()


if __name__ == "__main__":
    app()
