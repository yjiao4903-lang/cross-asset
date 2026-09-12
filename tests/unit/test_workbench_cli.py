"""Command-level regressions for Issue #20 run/trace CLI."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cross_asset.cli import app
from cross_asset.operations.workbench_run import (
    WorkbenchRun,
    persist_from_cli_payload,
    persist_run,
)

RUNNER = CliRunner()


def _persist_live(tmp_path: Path, run_id: str = "wb-cli-live") -> WorkbenchRun:
    run = WorkbenchRun(
        run_id=run_id,
        run_kind="daily",
        source_mode="LIVE",
        status="SUCCESS",
        model_version="workbench_v0.1",
        config_identity="cli-test",
        data_cutoff="2026-09-12",
        allocation_status="ACTIVE",
        weights={"CN_EQ": 0.4, "CASH": 0.6},
        components={
            "market": {"status": "AVAILABLE", "value": {"regime": "neutral"}},
            "allocation": {"status": "AVAILABLE", "value": {"CN_EQ": 0.4, "CASH": 0.6}},
            "data_health": {"status": "AVAILABLE", "value": {"CN_EQ": "OK"}},
        },
        provenance={"test": True},
    )
    persist_run(run, tmp_path)
    return run


def test_shadow_run_without_store_is_data_blocked_not_keyerror(tmp_path: Path):
    result = RUNNER.invoke(
        app,
        ["shadow-run", "--workbench-root", str(tmp_path), "--output-root", str(tmp_path / "shadow")],
    )
    assert result.exit_code == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "DATA_BLOCKED"
    assert "store_required" in payload["blockers"]
    assert payload["source_mode"] == "SIMULATED"
    assert "KeyError" not in result.stdout


def test_shadow_run_live_without_fetcher_is_data_blocked(tmp_path: Path):
    result = RUNNER.invoke(
        app,
        [
            "shadow-run",
            "--source-mode",
            "LIVE",
            "--database",
            str(tmp_path / "db.duckdb"),
            "--workbench-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["source_mode"] == "LIVE"
    assert payload["status"] == "DATA_BLOCKED"
    assert "live_fetcher_not_configured" in payload["blockers"]


def test_same_run_id_cross_traces_explain_report_and_data_health(tmp_path: Path):
    run = _persist_live(tmp_path)
    explained = RUNNER.invoke(app, ["explain-run", run.run_id, "--workbench-root", str(tmp_path)])
    reported = RUNNER.invoke(
        app,
        [
            "report-daily",
            "--run-id",
            run.run_id,
            "--workbench-root",
            str(tmp_path),
            "--output",
            str(tmp_path / "daily.md"),
        ],
    )
    health = RUNNER.invoke(
        app,
        [
            "data-health",
            "--run-id",
            run.run_id,
            "--workbench-root",
            str(tmp_path),
            "--output",
            str(tmp_path / "health.json"),
        ],
    )
    assert explained.exit_code == 0, explained.stdout
    assert reported.exit_code == 0, reported.stdout
    assert health.exit_code == 0, health.stdout
    explain_payload = json.loads(explained.stdout)
    report_payload = json.loads(reported.stdout)
    health_payload = json.loads(health.stdout)
    assert explain_payload["run_id"] == run.run_id
    assert report_payload["run_id"] == run.run_id
    assert health_payload["run_id"] == run.run_id
    assert explain_payload["source_mode"] == report_payload["source_mode"] == health_payload["source_mode"]
    assert explain_payload["components"]["style"]["status"] == "UNAVAILABLE"
    assert explain_payload["components"]["style"]["value"] is None
    report_text = Path(report_payload["output"]).read_text(encoding="utf-8")
    assert f"run_id: {run.run_id}" in report_text
    assert "source_mode: LIVE" in report_text
    assert "status: UNAVAILABLE" in report_text


def test_missing_run_id_is_failed_not_synthetic_success(tmp_path: Path):
    result = RUNNER.invoke(app, ["explain-run", "does-not-exist", "--workbench-root", str(tmp_path)])
    assert result.exit_code != 0
    assert "run_not_found" in result.stdout or "FAILED" in result.stdout


def test_run_daily_legacy_is_nonzero_reserved():
    result = RUNNER.invoke(app, ["run-daily", "--macro-source", "legacy"])
    assert result.exit_code != 0
    assert "interface reserved" in result.stdout
    assert "NOT_IMPLEMENTED" in result.stdout
    assert "RESERVED" in result.stdout


def test_launch_scripts_call_live_shadow_and_block_without_fetcher(tmp_path: Path):
    script_sh = Path("scripts/run_live_daily.sh").read_text(encoding="utf-8")
    script_ps = Path("scripts/run_live_daily.ps1").read_text(encoding="utf-8")
    assert "shadow-run" in script_sh and "--source-mode LIVE" in script_sh
    assert "shadow-run" in script_ps and "--source-mode LIVE" in script_ps
    assert "--workbench-root" in script_sh and "--workbench-root" in script_ps
    result = RUNNER.invoke(
        app,
        ["shadow-run", "--source-mode", "LIVE", "--workbench-root", str(tmp_path)],
    )
    assert result.exit_code == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "DATA_BLOCKED"
    assert payload["source_mode"] == "LIVE"
    assert (
        "live_fetcher_not_configured" in payload["blockers"]
        or "store_required" in payload["blockers"]
    )
    assert Path(payload["artifact_path"]).exists()


def test_shadow_live_restores_prior_formal_active_and_ignores_fixture(tmp_path: Path):
    formal = persist_from_cli_payload(
        {
            "run_id": "wb-formal-active",
            "status": "SUCCESS",
            "allocation_status": "ACTIVE",
            "weights": {"CN_EQ": 0.4, "CASH": 0.6},
            "macro_source": "marco",
            "data_cutoff": "2026-09-12",
        },
        run_kind="daily",
        source_mode="LIVE",
        root=tmp_path,
    )
    persist_from_cli_payload(
        {
            "run_id": "wb-fixture-noise",
            "status": "SUCCESS",
            "allocation_status": "ACTIVE",
            "weights": {"CN_EQ": 1.0},
            "data_cutoff": "2026-09-12",
        },
        run_kind="shadow",
        source_mode="FIXTURE",
        root=tmp_path,
    )
    persist_from_cli_payload(
        {
            "run_id": "wb-sim-noise",
            "status": "SUCCESS",
            "allocation_status": "ACTIVE",
            "weights": {"CASH": 1.0},
        },
        run_kind="shadow",
        source_mode="SIMULATED",
        root=tmp_path,
    )
    result = RUNNER.invoke(
        app,
        ["shadow-run", "--source-mode", "LIVE", "--workbench-root", str(tmp_path)],
    )
    assert result.exit_code == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["source_mode"] == "LIVE"
    assert payload["allocation_status"] == "FROZEN"
    assert payload["previous_valid_run_id"] == formal.run_id
    assert payload["previous_valid_source"] == "formal"
    assert payload["weights"] == {"CN_EQ": 0.4, "CASH": 0.6}
    assert payload["status"] == "DATA_BLOCKED"
    empty = RUNNER.invoke(
        app,
        ["shadow-run", "--source-mode", "LIVE", "--workbench-root", str(tmp_path / "empty")],
    )
    assert empty.exit_code == 2, empty.stdout
    empty_payload = json.loads(empty.stdout)
    assert empty_payload["allocation_status"] == "FROZEN"
    assert empty_payload["weights"] is None
    assert "previous_valid_formal_allocation_missing" in empty_payload["blockers"]
