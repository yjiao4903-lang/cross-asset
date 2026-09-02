import hashlib
import json
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from cross_asset.backtest.replay import FullModelStrategy
from cross_asset.cli import app
from cross_asset.integration.contracts import (
    ALLOCATABLE_ASSETS,
    BUNDLE_FILES,
    VIEWABLE_ASSETS,
    SnapshotStatus,
    marco_to_cross_asset_id,
    normalize_asset_id,
)
from cross_asset.integration.marco_provider import (
    MarcoIntegrationError,
    MarcoProvider,
    resolve_macro_source,
)
from cross_asset.storage import DuckDBStore

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "marco_integration_v1"
AS_OF = date(2026, 9, 2)


def _copy_fixture(tmp_path):
    target = tmp_path / "marco"
    shutil.copytree(FIXTURE, target)
    return target


def _seed_market_db(path, *, rows_per_series=80):
    series = {
        "CN_EQ_LARGE": (100.0, 0.60),
        "HK_EQ": (100.0, 0.45),
        "US_EQ": (100.0, 0.50),
        "CN_BOND_10Y": (2.5, -0.002),
        "GOLD": (1800.0, 1.20),
        "COPPER": (4.0, 0.006),
    }
    start = datetime(2026, 6, 1, 16, 0, 0, tzinfo=UTC)
    rows = []
    for index in range(rows_per_series):
        stamp = start + timedelta(days=index)
        for series_id, (base, slope) in series.items():
            rows.append(
                {
                    "series_id": series_id,
                    "observation_date": stamp.date(),
                    "available_at": stamp,
                    "value": base + slope * index,
                    "source": "fixture",
                    "source_series_id": series_id,
                    "vintage_date": None,
                    "ingested_at": stamp,
                    "quality": "ok",
                    "raw_file": None,
                }
            )
    store = DuckDBStore(path)
    try:
        store.insert_observations(rows, run_id="marco-run-daily-fixture")
    finally:
        store.close()


def _single_asset_observations():
    rows = []
    start = pd.Timestamp("2026-07-01")
    for index in range(40):
        day = start + pd.Timedelta(days=index)
        rows.append(
            {
                "series_id": "CN_EQ_LARGE",
                "observation_date": day.date(),
                "available_at": day.to_pydatetime(),
                "value": 100.0 + index,
            }
        )
    return pd.DataFrame(rows)


def test_fixture_matches_authoritative_four_file_contract_and_hashes():
    assert {path.name for path in FIXTURE.iterdir()} == set(BUNDLE_FILES)
    bundle = MarcoProvider(FIXTURE).load_bundle(at=AS_OF)
    assert bundle.report.status == "PASS"
    assert bundle.report.signal_status == "PARTIAL"
    assert bundle.manifest.schema_version == "1.0"
    assert bundle.macro_snapshot.factors.fiscal.status == SnapshotStatus.UNAVAILABLE
    assert bundle.macro_snapshot.factors.fiscal.score is None

    for name, manifest_file in bundle.manifest.files.items():
        digest = hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest()
        assert digest == manifest_file.sha256


def test_contract_pass_is_separate_from_signal_completeness():
    bundle = MarcoProvider(FIXTURE).load_bundle(at=AS_OF)
    fundamentals = {
        row.asset_id: row for row in bundle.fundamental_asset_view.assets
    }
    assert bundle.report.status == "PASS"
    assert bundle.report.signal_status == "PARTIAL"
    assert bundle.report.unavailable_factors == ["fiscal"]
    assert bundle.report.unavailable_assets == ["US_EQ", "CASH"]
    for asset_id in ("US_EQ", "CASH"):
        row = fundamentals[asset_id]
        assert row.status == SnapshotStatus.UNAVAILABLE
        assert row.fundamental_score is None
        assert row.confidence is None
        assert row.coverage is None


def test_manifest_hash_mismatch_fails_contract(tmp_path):
    target = _copy_fixture(tmp_path)
    path = target / "macro_snapshot.json"
    path.write_bytes(path.read_bytes() + b" ")
    report = MarcoProvider(target).validate(at=AS_OF)
    assert report.status == "FAIL"
    assert any(
        "SHA-256 mismatch for macro_snapshot.json" in error
        for error in report.errors
    )


def test_schema_mismatch_fails_contract(tmp_path):
    target = _copy_fixture(tmp_path)
    path = target / "integration_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = "2.0"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    report = MarcoProvider(target).validate(at=AS_OF)
    assert report.status == "FAIL"
    assert "schema mismatch" in report.errors[0]


def test_asset_boundary_keeps_marco_canonical_ids_at_boundary():
    bundle = MarcoProvider(FIXTURE).load_bundle(at=AS_OF)
    assert marco_to_cross_asset_id("CN_GOV_BOND") == "CN_BOND"
    assert marco_to_cross_asset_id("CN_CREDIT") is None
    assert normalize_asset_id("CN_GOV_BOND") == "CN_BOND"
    assert (
        bundle.cross_asset_fundamentals["CN_BOND"].asset_id
        == "CN_GOV_BOND"
    )
    assert (
        bundle.cross_asset_fundamentals["CN_BOND"].fundamental_score
        == 0.10
    )
    assert "CNY" not in ALLOCATABLE_ASSETS
    assert "CNY" in VIEWABLE_ASSETS
    assert [
        row.asset_id for row in bundle.fundamental_asset_view.fx_views
    ] == ["CNY"]


def test_marco_never_calls_legacy_factory_on_success_or_failure(tmp_path):
    calls = []

    def legacy():
        calls.append("called")
        return object()

    bundle = resolve_macro_source(
        "marco",
        integration_dir=FIXTURE,
        legacy_factory=legacy,
        at=AS_OF,
    )
    assert bundle.manifest.schema_version == "1.0"
    assert calls == []

    broken = _copy_fixture(tmp_path)
    (broken / "macro_snapshot.json").unlink()
    with pytest.raises(MarcoIntegrationError):
        resolve_macro_source(
            "marco",
            integration_dir=broken,
            legacy_factory=legacy,
            at=AS_OF,
        )
    assert calls == []


def test_fundamental_score_enters_asset_macro_directly_and_structure_stays_missing(
    monkeypatch,
):
    bundle = MarcoProvider(FIXTURE).load_bundle(at=AS_OF)

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "legacy build_macro_state must not run in Marco mode"
        )

    monkeypatch.setattr(
        "cross_asset.backtest.replay.build_macro_state",
        forbidden,
    )
    strategy = FullModelStrategy(
        ["CN_EQ"],
        asset_series_map={"CN_EQ": "CN_EQ_LARGE"},
        asset_signal_map={
            "CN_EQ": {"macro": "SHOULD_NOT_BE_USED"}
        },
        allocation_config={"constraints": {"max_weight": 1.0}},
    )
    strategy(
        _single_asset_observations(),
        datetime(2026, 9, 2, 23, 59, 59, tzinfo=UTC),
        macro_snapshot=bundle.macro_snapshot,
        fundamental_asset_view=bundle.fundamental_asset_view,
        structural_snapshot=bundle.structural_snapshot,
    )
    state = strategy.last_decision
    components = state["signal_components"]["CN_EQ"]
    assert state["macro_source"] == "marco"
    assert components["macro"]["score"] == 0.25
    assert components["macro"]["confidence"] == 0.8
    assert components["macro"]["coverage"] == 0.75
    assert components["structure"] is None
    assert (
        state["asset_scores"]["CN_EQ"].contributions["macro"]
        is not None
    )
    assert (
        state["integration_diagnostics"]["structural_snapshot"]
        is not None
    )


def test_unavailable_marco_fundamental_is_missing_not_zero(monkeypatch):
    bundle = MarcoProvider(FIXTURE).load_bundle(at=AS_OF)

    def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "legacy build_macro_state must not run in Marco mode"
        )

    monkeypatch.setattr(
        "cross_asset.backtest.replay.build_macro_state",
        forbidden,
    )
    rows = _single_asset_observations().copy()
    rows["series_id"] = "US_EQ"
    strategy = FullModelStrategy(
        ["US_EQ"],
        asset_series_map={"US_EQ": "US_EQ"},
        allocation_config={"constraints": {"max_weight": 1.0}},
    )
    strategy(
        rows,
        datetime(2026, 9, 2, 23, 59, 59, tzinfo=UTC),
        macro_snapshot=bundle.macro_snapshot,
        fundamental_asset_view=bundle.fundamental_asset_view,
        structural_snapshot=bundle.structural_snapshot,
    )
    assert (
        strategy.last_decision["signal_components"]["US_EQ"]["macro"]
        is None
    )
    assert (
        strategy.last_decision["asset_scores"]["US_EQ"]
        .contributions["macro"]
        is None
    )


def test_cli_validate_reports_contract_pass_with_partial_signals():
    result = CliRunner().invoke(
        app,
        [
            "validate-integration",
            "--integration-dir",
            str(FIXTURE),
            "--as-of",
            AS_OF.isoformat(),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "PASS"
    assert payload["signal_status"] == "PARTIAL"
    assert payload["legacy_fallback_used"] is False


def test_run_daily_marco_reaches_asset_score_and_allocation(tmp_path):
    database = tmp_path / "cross_asset.duckdb"
    _seed_market_db(database)
    result = CliRunner().invoke(
        app,
        [
            "run-daily",
            "--macro-source",
            "marco",
            "--integration-dir",
            str(FIXTURE),
            "--database",
            str(database),
            "--as-of",
            AS_OF.isoformat(),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "SUCCESS"
    assert payload["macro_source"] == "marco"
    assert payload["contract_status"] == "PASS"
    assert payload["signal_status"] == "PARTIAL"
    assert payload["allocation_status"] == "ACTIVE"
    assert set(payload["asset_scores"]) == set(ALLOCATABLE_ASSETS)
    assert set(payload["allocation"]) == set(ALLOCATABLE_ASSETS)
    assert (
        payload["asset_scores"]["US_EQ"]["contributions"]["macro"]
        is None
    )
    assert (
        payload["asset_scores"]["CASH"]["contributions"]["macro"]
        is None
    )
    assert payload["legacy_fallback_used"] is False


def test_run_daily_marco_is_explicitly_data_blocked_without_market_history(
    tmp_path,
):
    database = tmp_path / "empty.duckdb"
    result = CliRunner().invoke(
        app,
        [
            "run-daily",
            "--macro-source",
            "marco",
            "--integration-dir",
            str(FIXTURE),
            "--database",
            str(database),
            "--as-of",
            AS_OF.isoformat(),
        ],
    )
    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "DATA_BLOCKED"
    assert payload["allocation_status"] == "DATA_BLOCKED"
    assert payload["allocation"] is None
    assert payload["asset_scores"] == {}
    assert payload["legacy_fallback_used"] is False


def test_cli_legacy_behavior_remains_reserved():
    result = CliRunner().invoke(
        app,
        ["run-daily", "--macro-source", "legacy"],
    )
    assert result.exit_code == 0
    assert "interface reserved" in result.output
