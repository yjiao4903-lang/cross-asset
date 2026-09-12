"""Render explain/report/data-health views from one persisted workbench run."""

from __future__ import annotations

import json
from pathlib import Path

from cross_asset.operations.workbench_run import WorkbenchRun, component_view

COMPONENT_NAMES = ("market", "macro", "style", "asset", "allocation", "data_health")


def explain_workbench_run(run: WorkbenchRun) -> dict:
    return {
        "run_id": run.run_id,
        "run_kind": run.run_kind,
        "source_mode": run.source_mode,
        "status": run.status,
        "model_version": run.model_version,
        "config_identity": run.config_identity,
        "data_cutoff": run.data_cutoff,
        "allocation_status": run.allocation_status,
        "freeze_reason": run.freeze_reason,
        "previous_valid_run_id": run.previous_valid_run_id,
        "previous_valid_source": run.previous_valid_source,
        "weights": run.weights,
        "components": {name: component_view(run, name) for name in COMPONENT_NAMES},
        "warnings": list(run.warnings),
        "blockers": list(run.blockers),
        "provenance": dict(run.provenance),
        "artifact_path": run.artifact_path,
    }


def daily_report_from_run(run: WorkbenchRun, output: str | Path) -> Path:
    explained = explain_workbench_run(run)
    lines = [
        "# Daily Allocation Report",
        "",
        f"- run_id: {run.run_id}",
        f"- source_mode: {run.source_mode}",
        f"- status: {run.status}",
        f"- model_version: {run.model_version}",
        f"- data_cutoff: {run.data_cutoff or 'unavailable'}",
        f"- allocation_status: {run.allocation_status or 'unavailable'}",
        f"- freeze_reason: {run.freeze_reason or 'none'}",
        f"- previous_valid_run_id: {run.previous_valid_run_id or 'none'}",
        f"- previous_valid_source: {run.previous_valid_source or 'none'}",
        "",
    ]
    for name in COMPONENT_NAMES:
        view = explained["components"][name]
        status = view.get("status") if isinstance(view, dict) else "UNAVAILABLE"
        reason = view.get("reason") if isinstance(view, dict) else "data_gap"
        lines.extend(
            [f"## {name}", "", f"status: {status}", f"reason: {reason}", f"value: {view!r}", ""]
        )
    if run.blockers:
        lines.extend(["## Blockers", "", *[f"- {item}" for item in run.blockers], ""])
    if run.warnings:
        lines.extend(["## Warnings", "", *[f"- {item}" for item in run.warnings], ""])
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def data_health_from_run(run: WorkbenchRun, output: str | Path) -> dict:
    view = component_view(run, "data_health")
    payload = {
        "run_id": run.run_id,
        "source_mode": run.source_mode,
        "status": run.status,
        "data_cutoff": run.data_cutoff,
        "data_health": view,
        "blockers": list(run.blockers),
    }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    payload["output"] = str(path)
    return payload
