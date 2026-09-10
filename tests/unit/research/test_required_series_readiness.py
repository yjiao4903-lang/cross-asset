"""Regressions for the authoritative formal-research required-series set."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from cross_asset.backtest.returns import AssetReturnSpec
from cross_asset.research import executor
from cross_asset.research.dependencies import research_required_series_ids
from cross_asset.research.executor import ResearchModelConfig
from cross_asset.research.protocol import ResearchProtocol
from cross_asset.research.readiness import evaluate_research_readiness
from cross_asset.storage import init_db
from cross_asset.storage.acceptance_registry import upsert_data_acceptance


def _protocol() -> ResearchProtocol:
    return ResearchProtocol.from_mapping(
        {
            "version": "test-b01c",
            "status": "FROZEN",
            "owner": "owner",
            "reviewer": "reviewer",
            "approved_at": "2026-09-10T00:00:00Z",
            "windows": {
                "default_mode": "expanding",
                "train_min_years": 1,
                "test_window_months": 12,
                "step_months": 3,
                "rolling_years": None,
                "final_holdout": "last_20_percent",
            },
            "coverage_threshold": 1.0,
            "rebalance": "weekly",
            "transaction_cost_bps": [0],
            "base_cost_bps": 0,
            "turnover_convention": "two_sided_notional",
            "charge_initial_trade": False,
            "signal_model_version": "test",
            "benchmarks": ["STATIC", "FULL_MODEL"],
            "execution": {
                "require_protocol_status": "FROZEN",
                "holdout_release": False,
                "required_registry_status": "PASS",
                "required_usage_status": "RESEARCH_ADMISSIBLE",
                "require_all_critical_series": True,
            },
            "evaluation_thresholds": {
                "min_oos_observations": 1,
                "min_information_ratio_vs_static": 0.0,
                "min_annualized_excess_return_vs_static": 0.0,
                "max_drawdown_penalty_vs_static": 0.05,
            },
            "data_policy": {
                "project_status": "REAL_DATA_ADMISSION",
                "zero_imputation": False,
                "decision_cutoff": "available_at <= decision_time",
                "revision_policy": "latest_released_revision_per_observation_date",
            },
        }
    )


def _model(*, foreign: bool, macro: bool = False, hedge: bool = False) -> ResearchModelConfig:
    accounting = {
        "local_currency": "USD" if foreign else "CNY",
        "fx_mapping_status": "RESOLVED" if foreign else "NOT_REQUIRED",
        "fx": {"series_id": "FX_USD_CNY"} if foreign else None,
        "hedge_return_series_id": "USD_HEDGE" if hedge else None,
    }
    return ResearchModelConfig(
        assets=("ASSET",),
        strategic_weights={"ASSET": 1.0},
        return_specs={
            "ASSET": AssetReturnSpec(
                "ASSET_PRICE",
                kind="price",
                accounting=accounting,
            )
        },
        asset_signal_map={"ASSET": {"macro": None}},
        component_weights={"trend": 1.0},
        allocation_config={},
        macro_config={"series": {"MACRO_A": {}} if macro else {}, "dimensions": {}},
    )


def _catalog(store, series_id: str, *, stale_after_hours: float | None = 72, critical=False):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    store.conn.execute(
        """INSERT INTO series_catalog
           (series_id,display_name,frequency,unit,critical,point_in_time_class,
            stale_after_hours,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        [
            series_id,
            series_id,
            "daily",
            "index",
            critical,
            "market",
            stale_after_hours,
            now,
            now,
        ],
    )


def _approve(store, series_id: str) -> None:
    now = datetime(2025, 1, 1, tzinfo=UTC)
    upsert_data_acceptance(
        store,
        {
            "series_id": series_id,
            "provider": "manual",
            "source_series_id": series_id,
            "status": "PASS",
            "tech_gate": "PASS",
            "legal_gate": "PASS",
            "pit_gate": "PASS",
            "stability_gate": "PASS",
            "pit_grade": "B",
            "origin": "MANUAL",
            "permission_scope": "research",
            "semantic_equivalence": True,
            "manifest_hash": f"manifest-{series_id}",
            "reviewer": "reviewer",
            "approved_at": now,
            "evidence_json": "{}",
            "updated_at": now,
            "usage_status": "RESEARCH_ADMISSIBLE",
        },
    )


def _observe(
    store,
    series_id: str,
    observation_date: date,
    available_at: datetime,
    *,
    value: float,
    quality: str = "ok",
) -> None:
    store.insert_observations(
        [
            {
                "series_id": series_id,
                "observation_date": observation_date,
                "available_at": available_at,
                "value": value,
                "source": "manual",
                "source_series_id": series_id,
                "vintage_date": None,
                "ingested_at": available_at,
                "quality": quality,
                "raw_file": "b01c-fixture",
            }
        ],
        run_id=f"b01c-{series_id}-{available_at.isoformat()}-{quality}",
    )


def _make_ready(store, series_id: str) -> None:
    _catalog(store, series_id)
    _approve(store, series_id)
    _observe(
        store,
        series_id,
        date(2024, 1, 1),
        datetime(2024, 1, 2, 12, tzinfo=UTC),
        value=100.0,
    )
    _observe(
        store,
        series_id,
        date(2026, 1, 2),
        datetime(2026, 1, 2, 12, tzinfo=UTC),
        value=110.0,
    )


def test_required_series_includes_returns_accounting_and_macro_dependencies():
    model = _model(foreign=True, macro=True, hedge=True)

    assert research_required_series_ids(model) == (
        "ASSET_PRICE",
        "FX_USD_CNY",
        "MACRO_A",
        "USD_HEDGE",
    )


def test_executor_uses_the_same_authoritative_required_series(monkeypatch):
    model = _model(foreign=True, macro=True, hedge=True)
    expected = research_required_series_ids(model)
    captured = {}

    def stop_after_capture(
        _connection,
        _decision_time,
        *,
        required_usage_status,
        series_ids,
        market_data_cutoff=None,
    ):
        captured["usage"] = required_usage_status
        captured["series_ids"] = tuple(series_ids)
        raise RuntimeError("captured-required-series")

    monkeypatch.setattr(executor, "latest_formal_observations_asof", stop_after_capture)
    protocol = SimpleNamespace(
        execution_blockers=(),
        required_usage_status="RESEARCH_ADMISSIBLE",
    )
    plan = {
        "status": "READY_FOR_OOS",
        "holdout_sealed": True,
        "development_count": 1,
        "folds": [],
    }

    with pytest.raises(RuntimeError, match="captured-required-series"):
        executor.execute_walk_forward(
            object(),
            decision_dates=pd.to_datetime(
                ["2026-01-02T12:00:00Z", "2026-01-09T12:00:00Z"]
            ),
            plan=plan,
            protocol=protocol,
            model_config=model,
        )

    assert captured["usage"] == "RESEARCH_ADMISSIBLE"
    assert captured["series_ids"] == expected


@pytest.mark.parametrize(
    ("fx_state", "expected_reason"),
    [
        ("missing", "FX_USD_CNY:formal_observations_missing"),
        ("unapproved", "FX_USD_CNY:registry_pass_research_admissible_required"),
        ("stale", "FX_USD_CNY:pit_coverage_below_threshold"),
    ],
)
def test_foreign_asset_fx_dependency_fails_closed_at_readiness(
    fx_state: str,
    expected_reason: str,
):
    store = init_db(":memory:")
    decision = pd.Timestamp("2026-01-02T12:00:00Z")
    try:
        _make_ready(store, "ASSET_PRICE")
        if fx_state != "missing":
            _catalog(store, "FX_USD_CNY", stale_after_hours=24)
            _observe(
                store,
                "FX_USD_CNY",
                date(2024, 1, 1),
                datetime(2024, 1, 2, 12, tzinfo=UTC),
                value=7.0,
            )
        if fx_state == "stale":
            _approve(store, "FX_USD_CNY")
            _observe(
                store,
                "FX_USD_CNY",
                date(2026, 1, 2),
                datetime(2026, 1, 2, 8, tzinfo=UTC),
                value=7.1,
            )
            _observe(
                store,
                "FX_USD_CNY",
                date(2026, 1, 2),
                datetime(2026, 1, 2, 10, tzinfo=UTC),
                value=7.2,
                quality="stale",
            )

        required = research_required_series_ids(_model(foreign=True))
        result = evaluate_research_readiness(
            store.conn,
            _protocol(),
            required_series=required,
            decision_times=[decision],
        )
    finally:
        store.close()

    assert result["status"] == "BLOCKED"
    assert expected_reason in result["blockers"]
    assert {item["series_id"] for item in result["series"]} == set(required)


def test_reporting_currency_only_model_remains_ready_and_ignores_unrelated_catalog_critical():
    store = init_db(":memory:")
    decision = pd.Timestamp("2026-01-02T12:00:00Z")
    try:
        _make_ready(store, "ASSET_PRICE")
        # An unrelated catalog-critical series is not consumed by this effective
        # model and therefore must not silently expand the authoritative set.
        _catalog(store, "UNRELATED_CRITICAL", critical=True)
        required = research_required_series_ids(_model(foreign=False))
        result = evaluate_research_readiness(
            store.conn,
            _protocol(),
            required_series=required,
            decision_times=[decision],
        )
    finally:
        store.close()

    assert required == ("ASSET_PRICE",)
    assert result["status"] == "READY_FOR_OOS"
    assert [item["series_id"] for item in result["series"]] == ["ASSET_PRICE"]
