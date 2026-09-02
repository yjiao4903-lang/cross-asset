import pandas as pd

from cross_asset.backtest.returns import AssetReturnSpec
from cross_asset.research.evaluation import stitch_oos_path
from cross_asset.research.executor import ResearchModelConfig, execute_walk_forward
from cross_asset.research.plan import build_research_plan
from cross_asset.research.protocol import ResearchProtocol
from cross_asset.storage import init_db


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


def test_executor_runs_only_development_folds_and_keeps_holdout_sealed():
    store = init_db(":memory:")
    try:
        dates = pd.date_range(
            "2018-01-05T23:00:00Z",
            "2026-12-25T23:00:00Z",
            freq="W-FRI",
        )
        observations = []
        for index, decision in enumerate(dates):
            observations.append(
                {
                    "series_id": "A",
                    "observation_date": decision.date(),
                    "available_at": decision.tz_convert("UTC").tz_localize(None),
                    "value": 100.0 + index,
                    "source": "fixture",
                    "source_series_id": "A",
                    "vintage_date": None,
                    "ingested_at": decision.tz_convert("UTC").tz_localize(None),
                    "quality": "ok",
                    "raw_file": "fixture",
                }
            )
        store.insert_observations(observations, run_id="fixture")

        protocol = _protocol()
        plan = build_research_plan(dates, protocol)
        assert plan.status == "READY_FOR_OOS"
        config = ResearchModelConfig(
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
        rows = execute_walk_forward(
            store.conn,
            decision_dates=dates,
            plan=plan.to_dict(),
            protocol=protocol,
            model_config=config,
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
