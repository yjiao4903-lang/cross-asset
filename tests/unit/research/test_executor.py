from datetime import UTC, datetime

import pandas as pd
import pytest

from cross_asset.backtest.returns import AssetReturnSpec
from cross_asset.research.evaluation import stitch_oos_path
from cross_asset.research.executor import ResearchModelConfig, execute_walk_forward
from cross_asset.research.plan import build_research_plan
from cross_asset.research.protocol import ResearchProtocol
from cross_asset.storage import init_db
from cross_asset.storage.acceptance_registry import upsert_data_acceptance


def _protocol():
    return ResearchProtocol.from_mapping(
        {
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
            "transaction_cost_bps": [0, 10],
            "base_cost_bps": 10,
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
    )


def _model_config() -> ResearchModelConfig:
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


def _approve_research_source(store) -> None:
    now = datetime(2026, 9, 2, tzinfo=UTC)
    upsert_data_acceptance(
        store,
        {
            "series_id": "A",
            "provider": "manual",
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
            "manifest_hash": "executor-test-manifest",
            "reviewer": "reviewer",
            "approved_at": now,
            "evidence_json": "{}",
            "updated_at": now,
            "usage_status": "RESEARCH_ADMISSIBLE",
        },
    )


def _rows(dates, *, source: str, source_series_id: str, value_offset: float = 0.0):
    return [
        {
            "series_id": "A",
            "observation_date": decision.date(),
            "available_at": decision.tz_convert("UTC").tz_localize(None),
            "value": 100.0 + index + value_offset,
            "source": source,
            "source_series_id": source_series_id,
            "vintage_date": None,
            "ingested_at": decision.tz_convert("UTC").tz_localize(None),
            "quality": "ok",
            "raw_file": "executor-test",
        }
        for index, decision in enumerate(dates)
    ]


def test_executor_rejects_unapproved_candidate_observations():
    store = init_db(":memory:")
    try:
        dates = pd.date_range(
            "2018-01-05T23:00:00Z",
            "2026-12-25T23:00:00Z",
            freq="W-FRI",
        )
        store.insert_observations(
            _rows(dates, source="candidate", source_series_id="A.CANDIDATE"),
            run_id="candidate-only",
        )
        protocol = _protocol()
        plan = build_research_plan(dates, protocol)

        with pytest.raises(ValueError, match="formal_observations_empty"):
            execute_walk_forward(
                store.conn,
                decision_dates=dates,
                plan=plan.to_dict(),
                protocol=protocol,
                model_config=_model_config(),
            )
    finally:
        store.close()


def test_executor_runs_only_approved_development_data_and_keeps_holdout_sealed():
    store = init_db(":memory:")
    try:
        dates = pd.date_range(
            "2018-01-05T23:00:00Z",
            "2026-12-25T23:00:00Z",
            freq="W-FRI",
        )
        _approve_research_source(store)
        store.insert_observations(
            _rows(dates, source="manual", source_series_id="A"),
            run_id="approved-manual",
        )
        # A second, unapproved source for the same canonical series must remain
        # candidate-only and must never enter the formal research executor.
        store.insert_observations(
            _rows(
                dates,
                source="candidate",
                source_series_id="A.CANDIDATE",
                value_offset=10000.0,
            ),
            run_id="unapproved-alternative",
        )

        protocol = _protocol()
        plan = build_research_plan(dates, protocol)
        assert plan.status == "READY_FOR_OOS"
        rows = execute_walk_forward(
            store.conn,
            decision_dates=dates,
            plan=plan.to_dict(),
            protocol=protocol,
            model_config=_model_config(),
        )
        assert not rows.empty
        assert set(rows["benchmark"]) == {"STATIC", "FULL_MODEL"}
        assert pd.to_datetime(rows["decision_date"], utc=True).max() < pd.Timestamp(
            plan.holdout_start
        )
        stitched = stitch_oos_path(
            rows,
            plan.to_dict(),
            cost_bps=protocol.base_cost_bps,
            turnover_convention=protocol.turnover_convention,
            charge_initial_trade=protocol.charge_initial_trade,
        )
        assert not stitched.empty
        assert stitched["decision_date"].max() < pd.Timestamp(plan.holdout_start)
    finally:
        store.close()
