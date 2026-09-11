"""Regressions for fail-closed return-accounting readiness semantics."""

from datetime import UTC, date, datetime

import pandas as pd

from cross_asset.backtest.returns import AssetReturnSpec
from cross_asset.operations.execution_timing import (
    RESEARCH_PROXY_PERFORMANCE_SEMANTICS,
    RESEARCH_PROXY_RETURN_TIMING_BASIS,
)
from cross_asset.research.accounting_readiness import accounting_semantic_blockers
from cross_asset.research.dependencies import research_required_series_ids
from cross_asset.research.executor import ResearchModelConfig
from cross_asset.research.model_config import load_research_model_config
from cross_asset.research.protocol import ResearchProtocol
from cross_asset.research.readiness import evaluate_research_readiness
from cross_asset.storage import init_db
from cross_asset.storage.acceptance_registry import upsert_data_acceptance


def _protocol() -> ResearchProtocol:
    return ResearchProtocol.from_mapping(
        {
            "version": "test-b06",
            "status": "FROZEN",
            "owner": "owner",
            "reviewer": "reviewer",
            "approved_at": "2026-09-11T00:00:00Z",
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


def _accounting(
    *,
    local_currency: str = "CNY",
    return_type: str = "PRICE_RETURN",
    hedge_status: str = "UNHEDGED",
    fx_mapping_status: str = "NOT_REQUIRED",
    fx=None,
    hedge_return_series_id: str | None = None,
    futures_roll_semantics: str | None = None,
    policy_version: str = "test-b06",
) -> dict:
    return {
        "local_currency": local_currency,
        "return_type": return_type,
        "hedge_status": hedge_status,
        "fx_mapping_status": fx_mapping_status,
        "fx": fx,
        "hedge_return_series_id": hedge_return_series_id,
        "futures_roll_semantics": futures_roll_semantics,
        "policy_version": policy_version,
        "reporting_currency": "CNY",
        "supported_currencies": ["CNY", "USD", "HKD"],
        "pricing_basis": RESEARCH_PROXY_RETURN_TIMING_BASIS,
        "performance_semantics": RESEARCH_PROXY_PERFORMANCE_SEMANTICS,
    }


def _model(accounting: dict) -> ResearchModelConfig:
    return ResearchModelConfig(
        assets=("ASSET",),
        strategic_weights={"ASSET": 1.0},
        return_specs={"ASSET": AssetReturnSpec("ASSET_PRICE", accounting=accounting)},
        asset_signal_map={"ASSET": {"macro": None}},
        component_weights={"trend": 1.0},
        allocation_config={},
        macro_config={"series": {}, "dimensions": {}},
    )


def _make_series_ready(store, series_id: str) -> None:
    now = datetime(2026, 1, 2, 12, tzinfo=UTC)
    store.conn.execute(
        """INSERT INTO series_catalog
           (series_id,display_name,frequency,unit,critical,point_in_time_class,
            created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        [series_id, series_id, "daily", "index", False, "market", now, now],
    )
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
    store.insert_observations(
        [
            {
                "series_id": series_id,
                "observation_date": date(2024, 1, 1),
                "available_at": datetime(2024, 1, 2, 12, tzinfo=UTC),
                "value": 100.0,
                "source": "manual",
                "source_series_id": series_id,
                "vintage_date": None,
                "ingested_at": now,
                "quality": "ok",
                "raw_file": "b06-fixture",
            },
            {
                "series_id": series_id,
                "observation_date": date(2026, 1, 2),
                "available_at": now,
                "value": 110.0,
                "source": "manual",
                "source_series_id": series_id,
                "vintage_date": None,
                "ingested_at": now,
                "quality": "ok",
                "raw_file": "b06-fixture",
            },
        ],
        run_id=f"b06-{series_id}",
    )


def test_current_default_model_exposes_accounting_semantic_blockers_at_readiness():
    model = load_research_model_config()
    store = init_db(":memory:")
    try:
        result = evaluate_research_readiness(
            store.conn,
            _protocol(),
            required_series=research_required_series_ids(model),
            accounting_return_specs=model.return_specs,
        )
    finally:
        store.close()

    accounting = set(result["accounting_semantic_blockers"])
    assert result["status"] == "BLOCKED"
    assert "accounting:HK_EQ:fx_mapping_unresolved" in accounting
    assert "accounting:US_EQ:fx_mapping_unresolved" in accounting
    assert "accounting:GOLD:return_type_unresolved" in accounting
    assert "accounting:COMMODITY:futures_roll_semantics_unverified" in accounting
    assert "accounting:COMMODITY:fx_mapping_unresolved" in accounting


def test_reporting_currency_only_resolved_model_can_be_ready_when_data_is_ready():
    model = _model(_accounting())
    store = init_db(":memory:")
    decision = pd.Timestamp("2026-01-02T12:00:00Z")
    try:
        _make_series_ready(store, "ASSET_PRICE")
        result = evaluate_research_readiness(
            store.conn,
            _protocol(),
            required_series=research_required_series_ids(model),
            decision_times=[decision],
            accounting_return_specs=model.return_specs,
        )
    finally:
        store.close()

    assert result["accounting_semantic_blockers"] == []
    assert result["status"] == "READY_FOR_OOS"


def test_resolved_foreign_fx_moves_to_ordinary_required_series_readiness():
    fx = {
        "series_id": "FX_USD_CNY",
        "local_currency": "USD",
        "reporting_currency": "CNY",
        "quote_direction": "reporting_per_local",
        "max_age_hours": 72,
    }
    model = _model(
        _accounting(
            local_currency="USD",
            fx_mapping_status="RESOLVED",
            fx=fx,
        )
    )
    assert accounting_semantic_blockers(model.return_specs) == ()
    assert research_required_series_ids(model) == ("ASSET_PRICE", "FX_USD_CNY")

    store = init_db(":memory:")
    try:
        _make_series_ready(store, "ASSET_PRICE")
        result = evaluate_research_readiness(
            store.conn,
            _protocol(),
            required_series=research_required_series_ids(model),
            accounting_return_specs=model.return_specs,
        )
    finally:
        store.close()

    assert result["accounting_semantic_blockers"] == []
    assert "FX_USD_CNY:formal_observations_missing" in result["blockers"]
    assert "FX_USD_CNY:registry_pass_research_admissible_required" in result["blockers"]


def test_unverified_futures_roll_and_missing_hedge_contract_fail_closed():
    futures_model = _model(
        _accounting(
            local_currency="USD",
            return_type="FUTURES_CONTINUOUS_ROLL_PROXY",
            fx_mapping_status="RESOLVED",
            fx={
                "series_id": "FX_USD_CNY",
                "local_currency": "USD",
                "reporting_currency": "CNY",
                "quote_direction": "reporting_per_local",
                "max_age_hours": 72,
            },
            futures_roll_semantics="UNVERIFIED",
        )
    )
    hedged_model = _model(
        _accounting(
            local_currency="USD",
            hedge_status="HEDGED",
            fx_mapping_status="UNRESOLVED",
        )
    )

    assert (
        "accounting:ASSET:futures_roll_semantics_unverified"
        in accounting_semantic_blockers(futures_model.return_specs)
    )
    assert (
        "accounting:ASSET:hedge_return_series_missing"
        in accounting_semantic_blockers(hedged_model.return_specs)
    )


def test_missing_fx_contract_and_policy_inconsistency_fail_closed():
    foreign = _model(
        _accounting(local_currency="USD", fx_mapping_status="RESOLVED", fx=None)
    )
    assert (
        "accounting:ASSET:fx_contract_missing"
        in accounting_semantic_blockers(foreign.return_specs)
    )

    left = AssetReturnSpec("LEFT", accounting=_accounting(policy_version="v1"))
    right = AssetReturnSpec("RIGHT", accounting=_accounting(policy_version="v2"))
    blockers = accounting_semantic_blockers({"LEFT": left, "RIGHT": right})
    assert blockers == ("accounting:policy:embedded_accounting_policy_inconsistent",)
