import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from cross_asset.backtest.replay import FullModelStrategy
from cross_asset.cli import app
from cross_asset.integration.contracts import (
    ALLOCATABLE_ASSETS,
    VIEWABLE_ASSETS,
    normalize_asset_id,
)
from cross_asset.integration.marco_provider import (
    MarcoIntegrationError,
    MarcoProvider,
    resolve_macro_source,
)

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "marco_integration_v1"
)
AT = datetime(2026, 9, 2, 12, tzinfo=UTC)


def _copy_fixture(tmp_path):
    target = tmp_path / "marco"
    shutil.copytree(FIXTURE, target)
    return target


def _rewrite(path, mutate):
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_contract_assets_and_aliases_are_explicit():
    assert set(ALLOCATABLE_ASSETS) < set(VIEWABLE_ASSETS)
    assert normalize_asset_id("SPX") == "US_EQ"
    assert normalize_asset_id("xau") == "GOLD"
    assert normalize_asset_id("usd-cnh") == "USDCNH"
    with pytest.raises(ValueError):
        normalize_asset_id("UNKNOWN_ASSET")


def test_marco_fixture_validates_and_normalizes_aliases():
    bundle = MarcoProvider(FIXTURE).load_bundle(at=AT)
    assert bundle.report.status == "PASS"
    assert bundle.report.legacy_fallback_used is False
    assert bundle.report.normalized_asset_ids == ["US_EQ", "GOLD", "CN_EQ"]
    assert [view.asset_id for view in bundle.allocatable_views] == [
        "US_EQ",
        "GOLD",
        "CN_EQ",
    ]


def test_missing_score_is_degraded_and_never_zero_filled(tmp_path):
    target = _copy_fixture(tmp_path)

    def mutate(payload):
        payload["dimensions"]["GROWTH"]["score"] = None

    _rewrite(target / "macro_state.json", mutate)
    bundle = MarcoProvider(target).load_bundle(at=AT)
    assert bundle.report.status == "DEGRADED"
    assert bundle.macro_state.dimensions["GROWTH"].score is None
    assert any(
        "no zero imputation" in item for item in bundle.report.warnings
    )


def test_stale_bundle_is_explicitly_degraded(tmp_path):
    target = _copy_fixture(tmp_path)

    def mutate(payload):
        payload["status"] = "STALE"

    _rewrite(target / "manifest.json", mutate)
    report = MarcoProvider(target).validate(at=AT)
    assert report.status == "DEGRADED"
    assert report.exit_code == 2


def test_schema_mismatch_fails(tmp_path):
    target = _copy_fixture(tmp_path)

    def mutate(payload):
        payload["contract_version"] = "2.0"

    _rewrite(target / "macro_state.json", mutate)
    report = MarcoProvider(target).validate(at=AT)
    assert report.status == "FAIL"
    assert report.exit_code == 1
    assert "schema mismatch" in report.errors[0]


def test_marco_never_calls_legacy_factory_on_success_or_failure(tmp_path):
    calls = []

    def legacy():
        calls.append("called")
        return object()

    state = resolve_macro_source(
        "marco",
        integration_dir=FIXTURE,
        legacy_factory=legacy,
        at=AT,
    )
    assert state.model_version == "marco_macro_v1"
    assert calls == []

    broken = _copy_fixture(tmp_path)
    (broken / "macro_state.json").unlink()
    with pytest.raises(MarcoIntegrationError):
        resolve_macro_source(
            "marco",
            integration_dir=broken,
            legacy_factory=legacy,
            at=AT,
        )
    assert calls == []


def test_full_model_accepts_external_marco_macro_without_legacy_call(
    monkeypatch,
):
    macro = MarcoProvider(FIXTURE).load_macro_state(at=AT)

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "legacy macro engine must not be called in Marco mode"
        )

    monkeypatch.setattr(
        "cross_asset.backtest.replay.build_macro_state",
        forbidden,
    )
    rows = []
    start = pd.Timestamp("2020-01-01", tz="UTC")
    for i in range(30):
        day = start + pd.Timedelta(days=i)
        for asset, slope in (("A", 1.0), ("B", 0.4)):
            rows.append(
                {
                    "series_id": asset,
                    "observation_date": day.date(),
                    "available_at": day,
                    "value": 100.0 + slope * i,
                }
            )
    info = pd.DataFrame(rows)
    strategy = FullModelStrategy(
        ["A", "B"],
        asset_signal_map={
            "A": {"macro": "GROWTH"},
            "B": {"macro": "GROWTH"},
        },
    )
    decision = datetime(2020, 2, 1, tzinfo=UTC)
    strategy(info, decision, macro_state=macro)
    assert strategy.last_decision["macro_state"] is macro
    assert (
        strategy.last_decision["model_versions"]["macro"]
        == "marco_macro_v1"
    )


def test_cli_validate_and_run_daily_marco():
    runner = CliRunner()
    validate = runner.invoke(
        app,
        [
            "validate-integration",
            "--integration-dir",
            str(FIXTURE),
            "--as-of",
            AT.isoformat(),
        ],
    )
    assert validate.exit_code == 0, validate.output
    assert json.loads(validate.output)["status"] == "PASS"

    daily = runner.invoke(
        app,
        [
            "run-daily",
            "--macro-source",
            "marco",
            "--integration-dir",
            str(FIXTURE),
            "--as-of",
            AT.isoformat(),
        ],
    )
    assert daily.exit_code == 0, daily.output
    payload = json.loads(daily.output)
    assert payload["macro_source"] == "marco"
    assert payload["legacy_fallback_used"] is False
    assert (
        payload["macro_state"]["dimensions"]["GROWTH"]["score"]
        == 0.6
    )


def test_cli_legacy_behavior_remains_reserved():
    result = CliRunner().invoke(
        app,
        ["run-daily", "--macro-source", "legacy"],
    )
    assert result.exit_code == 0
    assert "interface reserved" in result.output
