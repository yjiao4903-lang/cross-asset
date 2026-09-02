from datetime import datetime

from cross_asset.research.protocol import ResearchProtocol
from cross_asset.research.readiness import evaluate_research_readiness
from cross_asset.storage import init_db

RAW = {
    "version": "0.3",
    "status": "PLANNING_ONLY",
    "owner": "TBD",
    "reviewer": "TBD",
    "approved_at": "TBD",
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
    "transaction_cost_bps": [0, 5, 10, 20, 30],
    "turnover_convention": "two_sided_notional",
    "charge_initial_trade": False,
    "signal_model_version": "full_model_v0.2",
    "benchmarks": ["STATIC", "TREND_ONLY", "MACRO_ONLY", "RISK_ONLY", "FULL_MODEL"],
    "execution": {
        "require_protocol_status": "FROZEN",
        "holdout_release": False,
        "required_registry_status": "PASS",
        "required_usage_status": "RESEARCH_ADMISSIBLE",
        "require_all_critical_series": True,
    },
    "evaluation_thresholds": {
        "min_oos_observations": 52,
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


def test_readiness_blocks_empty_formal_store():
    store = init_db(":memory:")
    try:
        store.conn.execute(
            """INSERT INTO series_catalog
               (series_id,display_name,frequency,unit,critical,point_in_time_class,created_at,updated_at)
               VALUES ('A','A','daily','price',TRUE,'market',?,?)""",
            [datetime(2026, 1, 1), datetime(2026, 1, 1)],
        )
        result = evaluate_research_readiness(
            store.conn,
            ResearchProtocol.from_mapping(RAW),
        )
        assert result["status"] == "BLOCKED"
        assert "formal_observations_empty" in result["blockers"]
        assert any("registry_pass_research_admissible_required" in item for item in result["blockers"])
    finally:
        store.close()
