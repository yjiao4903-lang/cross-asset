"""Top-level PERSONAL_WEEKLY CLI smoke coverage."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cross_asset.cli import app

ROOT = Path(__file__).resolve().parents[2]
RUNNER = CliRunner()


def _json_stdout(result) -> dict:
    assert result.exit_code == 0, result.stdout
    return json.loads(result.stdout)


def test_top_level_help_keeps_existing_commands_and_adds_weekly_commands():
    result = RUNNER.invoke(app, ["--help"])
    assert result.exit_code == 0, result.stdout
    for command in (
        "validate-data-file",
        "register-data-acceptance",
        "coverage-report",
        "probe-data",
        "run-daily",
        "report-daily",
        "backtest",
        "weekly-review",
        "claim-ledger",
        "scenario",
    ):
        assert command in result.stdout


def test_weekly_review_top_level_cli_smoke(tmp_path: Path):
    payload = _json_stdout(
        RUNNER.invoke(
            app,
            [
                "weekly-review",
                "--as-of",
                "2026-09-05",
                "--week-end",
                "2026-09-04",
                "--review-cutoff",
                "2026-09-05T12:00:00+08:00",
                "--observations-json",
                str(ROOT / "examples" / "weekly_review_fixture.json"),
                "--output",
                str(tmp_path / "weekly_review.md"),
                "--snapshot-output",
                str(tmp_path / "weekly_review.snapshot.json"),
            ],
        )
    )
    assert payload["status"] == "READY"
    assert payload["usage"] == "PERSONAL_WEEKLY"
    assert payload["admission"] == "DEVELOPMENT_PRIOR"
    assert payload["stance"]["stance"] == "HOLD"
    assert payload["stance"]["decision"] == "不行动"


def test_claim_ledger_top_level_cli_smoke_is_append_only_across_reload(tmp_path: Path):
    ledger_path = tmp_path / "claim_ledger.jsonl"
    args = [
        "claim-ledger",
        "--input",
        str(ROOT / "examples" / "event_claims_fixture.json"),
        "--now",
        "2026-10-02T00:00:00+00:00",
        "--ledger-output",
        str(ledger_path),
    ]
    first = _json_stdout(RUNNER.invoke(app, args))
    second = _json_stdout(RUNNER.invoke(app, args))
    assert first["status"] == "DEVELOPMENT_PRIOR"
    assert len(first["claims"]) == 1
    assert len(second["claims"]) == 1
    assert ledger_path.read_text(encoding="utf-8").count('"kind": "claim"') == 1


def test_scenario_top_level_cli_smoke_and_missing_input_is_unestimated(tmp_path: Path):
    good = _json_stdout(
        RUNNER.invoke(
            app,
            [
                "scenario",
                "--input",
                str(ROOT / "examples" / "scenario_fixture.json"),
                "--output",
                str(tmp_path / "scenarios.json"),
            ],
        )
    )
    assert good["status"] == "DEVELOPMENT_PRIOR"
    assert all(item["status"] == "ESTIMATED_SCENARIO" for item in good["results"])

    missing = _json_stdout(
        RUNNER.invoke(
            app,
            [
                "scenario",
                "--input",
                str(ROOT / "examples" / "scenario_missing_fx_fixture.json"),
                "--output",
                str(tmp_path / "scenarios_missing.json"),
            ],
        )
    )
    assert missing["results"][0]["status"] == "UNESTIMATED"
    assert "fx_shock" in missing["results"][0]["missing_fields"]
