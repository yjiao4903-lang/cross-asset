import pandas as pd
import pytest

from cross_asset.research.evaluation import (
    paired_oos_metrics,
    stitch_oos_path,
    stitch_oos_returns,
    verdict_from_thresholds,
)


def test_stitch_prefers_latest_fold_and_rejects_holdout_leak():
    plan = {
        "holdout_sealed": True,
        "holdout_start": "2026-07-01T00:00:00+00:00",
        "folds": [
            {
                "fold": 0,
                "test_start": "2026-01-01T00:00:00+00:00",
                "test_end": "2026-06-30T00:00:00+00:00",
            },
            {
                "fold": 1,
                "test_start": "2026-04-01T00:00:00+00:00",
                "test_end": "2026-06-30T00:00:00+00:00",
            },
        ],
    }
    frame = pd.DataFrame(
        [
            {"fold": 0, "decision_date": "2026-04-03", "benchmark": "FULL_MODEL", "net_return": 0.01},
            {"fold": 1, "decision_date": "2026-04-03", "benchmark": "FULL_MODEL", "net_return": 0.02},
        ]
    )
    stitched = stitch_oos_returns(frame, plan)
    assert len(stitched) == 1
    assert stitched.iloc[0]["net_return"] == pytest.approx(0.02)

    leaked = frame.copy()
    leaked.loc[0, "decision_date"] = "2026-07-03"
    with pytest.raises(ValueError):
        stitch_oos_returns(leaked, plan)


def test_paired_metrics_and_predeclared_verdict():
    index = pd.date_range("2025-01-03", periods=60, freq="W-FRI")
    model = pd.Series([0.009, 0.011] * 30, index=index)
    static = pd.Series([0.005] * 60, index=index)
    metrics = paired_oos_metrics(model, static)
    result = verdict_from_thresholds(
        metrics,
        {
            "min_oos_observations": 52,
            "min_information_ratio_vs_static": 0.0,
            "min_annualized_excess_return_vs_static": 0.0,
            "max_drawdown_penalty_vs_static": 0.05,
        },
    )
    assert metrics["observations"] == 60
    assert metrics["annualized_excess_return"] > 0
    assert result["verdict"] == "ACCEPT"



def test_stitched_path_recomputes_turnover_after_fold_selection():
    plan = {
        "holdout_sealed": True,
        "holdout_start": "2026-07-01T00:00:00+00:00",
        "folds": [
            {
                "fold": 0,
                "test_start": "2026-01-01T00:00:00+00:00",
                "test_end": "2026-06-30T00:00:00+00:00",
            },
            {
                "fold": 1,
                "test_start": "2026-04-01T00:00:00+00:00",
                "test_end": "2026-06-30T00:00:00+00:00",
            },
        ],
    }
    frame = pd.DataFrame(
        [
            {
                "fold": 0,
                "decision_date": "2026-04-03T00:00:00Z",
                "benchmark": "FULL_MODEL",
                "gross_return": 0.01,
                "weights": {"A": 1.0},
            },
            {
                "fold": 1,
                "decision_date": "2026-04-03T00:00:00Z",
                "benchmark": "FULL_MODEL",
                "gross_return": 0.02,
                "weights": {"A": 0.5, "B": 0.5},
            },
            {
                "fold": 1,
                "decision_date": "2026-04-10T00:00:00Z",
                "benchmark": "FULL_MODEL",
                "gross_return": 0.01,
                "weights": {"A": 1.0, "B": 0.0},
            },
        ]
    )
    stitched = stitch_oos_path(
        frame,
        plan,
        cost_bps=10,
        turnover_convention="two_sided_notional",
        charge_initial_trade=False,
    )
    assert len(stitched) == 2
    assert stitched.iloc[0]["turnover"] == 0
    assert stitched.iloc[1]["turnover"] == pytest.approx(1.0)
    assert stitched.iloc[1]["net_return"] == pytest.approx(0.009)
