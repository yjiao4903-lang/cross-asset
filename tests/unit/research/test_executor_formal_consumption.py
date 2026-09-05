"""Cross-entry consistency: research consumes the same approved selection.

The walk-forward executor and the daily path must both read market data
through the single shared approved-provenance query; an unapproved source
with fresher vintages can never leak into either entry point.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from cross_asset.backtest.returns import AssetReturnSpec, portfolio_period_return
from cross_asset.research.executor import ResearchModelConfig, execute_walk_forward
from cross_asset.research.plan import build_research_plan
from cross_asset.research.protocol import ResearchProtocol
from cross_asset.storage import init_db, latest_formal_observations_asof
from cross_asset.storage.acceptance_registry import upsert_data_acceptance

PROTOCOL_RAW = {
    "version": "0.3",
    "status": "FROZEN",
    "owner": "owner",
    "reviewer": "reviewer",
    "approved_at": "2026-09-02T10:00:00+08:00",
    "windows": {
        "default_mode": "expanding",
        "train_min_years": 5,
        "test_window_months": 12,
        "step_months": 3,
        "rolling_years": None,
        "final_holdout": "last_20_percent",
    },
    "coverage_threshold": 0.95,
    "rebalance": "weekly",
    "transaction_cost_bps": [0],
    "base_cost_bps": 0,
    "turnover_convention": "two_sided_notional",
    "charge_initial_trade": False,
    "signal_model_version": "full_model_v0.2",
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


def _protocol():
    return ResearchProtocol.from_mapping(dict(PROTOCOL_RAW))


def _observe(store, *, source, value_base, available_hour):
    dates = pd.date_range("2018-01-05T23:00:00Z", "2026-12-25T23:00:00Z", freq="W-FRI")
    rows = []
    for index, decision in enumerate(dates):
        available_at = (
            decision.tz_convert("UTC").tz_localize(None) + pd.Timedelta(hours=available_hour)
        )
        rows.append(
            {
                "series_id": "A",
                "observation_date": decision.date(),
                "available_at": available_at.to_pydatetime(),
                "value": value_base + index,
                "source": source,
                "source_series_id": "A",
                "vintage_date": None,
                "ingested_at": available_at.to_pydatetime(),
                "quality": "ok",
                "raw_file": "consistency-fixture",
            }
        )
    store.insert_observations(rows, run_id=f"consistency-{source}")


def _approve(store, provider="srcA"):
    upsert_data_acceptance(
        store,
        {
            "series_id": "A",
            "provider": provider,
            "source_series_id": "A",
            "status": "PASS",
            "tech_gate": "PASS",
            "legal_gate": "PASS",
            "pit_gate": "PASS",
            "stability_gate": "PASS",
            "pit_grade": "B",
            "origin": "MANUAL",
            "permission_scope": "research",
            "semantic_equivalence": True,
            "manifest_hash": "manifest-consistency",
            "reviewer": "reviewer",
            "approved_at": datetime(2017, 1, 1, tzinfo=UTC),
            "evidence_json": "{}",
            "updated_at": datetime(2017, 1, 1, tzinfo=UTC),
            "usage_status": "RESEARCH_ADMISSIBLE",
        },
    )


def _config():
    return ResearchModelConfig(
        assets=("A", "CASH"),
        strategic_weights={"A": 0.5, "CASH": 0.5},
        return_specs={
            "A": AssetReturnSpec("A", kind="price"),
            "CASH": AssetReturnSpec(None, kind="cash"),
        },
        asset_signal_map={"A": {"macro": None}, "CASH": {"macro": None}},
        component_weights={"trend": 1.0},
        allocation_config={
            "constraints": {
                "max_tactical_tilt": 0.10,
                "min_weight": 0.0,
                "max_weight": 1.0,
            }
        },
        macro_config={"series": {}, "dimensions": {}},
    )


def test_research_and_shared_query_select_the_same_approved_provenance():
    store = _store()
    try:
        # Approved source carries values 100+i; an unapproved source with
        # later available_at carries values 999+i for the same dates.
        _observe(store, source="srcA", value_base=100.0, available_hour=1)
        _observe(store, source="srcB", value_base=999.0, available_hour=5)
        _approve(store, provider="srcA")

        dates = pd.date_range("2018-01-05T23:00:00Z", "2026-12-25T23:00:00Z", freq="W-FRI")
        protocol = _protocol()
        plan = build_research_plan(dates, protocol)
        rows = execute_walk_forward(
            store.conn,
            decision_dates=dates,
            plan=plan.to_dict(),
            protocol=protocol,
            model_config=_config(),
        )
        static_rows = rows[rows["benchmark"] == "STATIC"]

        formal = latest_formal_observations_asof(
            store.conn,
            datetime.now(UTC),
            required_usage_status="RESEARCH_ADMISSIBLE",
        )
        assert set(formal["source"]) == {"srcA"}

        checked = 0
        for _fold, group in static_rows.groupby("fold"):
            decisions = pd.to_datetime(group["decision_date"], utc=True).tolist()
            for position, (_, row) in enumerate(group.iterrows()):
                next_decision = (
                    decisions[position + 1]
                    if position + 1 < len(decisions)
                    else None
                )
                if next_decision is None:
                    continue
                expected = portfolio_period_return(
                    formal,
                    {"A": 0.5, "CASH": 0.5},
                    decisions[position],
                    next_decision,
                    specs=_config().return_specs,
                )
                assert row["gross_return"] == pytest.approx(expected)
                checked += 1
        assert checked > 0
    finally:
        store.close()


def test_executor_blocks_when_only_unapproved_provenance_exists():
    store = _store()
    try:
        _observe(store, source="srcB", value_base=999.0, available_hour=1)
        dates = pd.date_range("2018-01-05T23:00:00Z", "2026-12-25T23:00:00Z", freq="W-FRI")
        protocol = _protocol()
        plan = build_research_plan(dates, protocol)
        try:
            execute_walk_forward(
                store.conn,
                decision_dates=dates,
                plan=plan.to_dict(),
                protocol=protocol,
                model_config=_config(),
            )
        except ValueError as exc:
            assert "formal_observations_empty" in str(exc)
        else:
            raise AssertionError("executor consumed unapproved provenance")
    finally:
        store.close()


def _store():
    return init_db(":memory:")
