import json

import pandas as pd
import pytest

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
    "base_cost_bps": 10,
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


def test_planning_protocol_builds_sealed_plan_but_blocks_execution():
    from cross_asset import research

    protocol = research.ResearchProtocol.from_mapping(RAW)
    dates = pd.date_range("2015-01-02", "2026-12-25", freq="W-FRI", tz="UTC")
    plan = research.build_research_plan(dates, protocol)
    assert plan.holdout_sealed is True
    assert plan.holdout_dates == ()
    assert plan.holdout_count > 0
    assert plan.fold_count > 0
    assert plan.status == "BLOCKED"
    assert "protocol_status_requires_frozen" in plan.blockers
    assert "protocol_owner_reviewer_approval_required" in plan.blockers


def test_frozen_approved_protocol_is_ready_with_enough_dates():
    from cross_asset import research

    raw = json.loads(json.dumps(RAW))
    raw.update(
        {
            "status": "FROZEN",
            "owner": "owner",
            "reviewer": "reviewer",
            "approved_at": "2026-09-02T10:00:00+08:00",
        }
    )
    protocol = research.ResearchProtocol.from_mapping(raw)
    dates = pd.date_range("2015-01-02", "2026-12-25", freq="W-FRI", tz="UTC")
    plan = research.build_research_plan(dates, protocol)
    assert plan.status == "READY_FOR_OOS"
    assert plan.holdout_sealed is True
    assert plan.development_end < plan.holdout_start


def test_decision_date_loader_rejects_duplicates(tmp_path):
    from cross_asset import research

    path = tmp_path / "dates.json"
    path.write_text(json.dumps(["2026-01-02T00:00:00Z", "2026-01-02T00:00:00Z"]), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        research.load_decision_dates(path)
