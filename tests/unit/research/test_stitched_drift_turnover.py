import math

import pandas as pd
import pytest

from cross_asset.research.evaluation import stitch_oos_path

PLAN = {
    "holdout_sealed": True,
    "holdout_start": "2026-02-01T00:00:00+00:00",
    "folds": [
        {
            "fold": 0,
            "test_start": "2026-01-02T00:00:00+00:00",
            "test_end": "2026-01-30T00:00:00+00:00",
        }
    ],
}


def _frame(first_asset_returns):
    return pd.DataFrame(
        [
            {
                "fold": 0,
                "decision_date": "2026-01-02T00:00:00Z",
                "benchmark": "FULL_MODEL",
                "gross_return": 0.10,
                "asset_returns": first_asset_returns,
                "weights": {"A": 0.5, "B": 0.5},
            },
            {
                "fold": 0,
                "decision_date": "2026-01-09T00:00:00Z",
                "benchmark": "FULL_MODEL",
                "gross_return": 0.0,
                "asset_returns": {"A": 0.0, "B": 0.0},
                "weights": {"A": 0.5, "B": 0.5},
            },
            {
                "fold": 0,
                "decision_date": "2026-01-16T00:00:00Z",
                "benchmark": "FULL_MODEL",
                "gross_return": float("nan"),
                "asset_returns": None,
                "weights": {"A": 0.5, "B": 0.5},
            },
        ]
    )


def test_stitched_path_rebalances_from_drifted_pretrade_holdings():
    stitched = stitch_oos_path(
        _frame({"A": 0.20, "B": 0.0}),
        PLAN,
        cost_bps=10,
        turnover_convention="two_sided_notional",
        charge_initial_trade=False,
    )

    assert stitched.iloc[0]["turnover"] == 0.0
    assert stitched.iloc[1]["turnover"] == pytest.approx(1.0 / 11.0)
    assert stitched.iloc[1]["pretrade_weights"] == pytest.approx(
        {"A": 1.2 / 2.2, "B": 1.0 / 2.2}
    )
    assert stitched.iloc[1]["turnover_basis"] == "drifted_pretrade_holdings"
    assert stitched.iloc[1]["net_return"] == pytest.approx(
        -(1.0 / 11.0) * 10 / 10000
    )
    assert bool(stitched.iloc[1]["drift_aware_turnover"]) is True
    assert stitched.iloc[2]["turnover"] == 0.0
    assert stitched.iloc[2]["turnover_basis"] == "terminal_no_trade"
    assert math.isnan(stitched.iloc[2]["net_return"])


def test_stitched_path_fails_closed_when_prior_holding_return_is_missing():
    stitched = stitch_oos_path(
        _frame({"A": 0.20}),
        PLAN,
        cost_bps=10,
        turnover_convention="two_sided_notional",
        charge_initial_trade=False,
    )

    assert stitched.iloc[1]["turnover_basis"] == "drift_unavailable"
    assert math.isnan(stitched.iloc[1]["turnover"])
    assert math.isnan(stitched.iloc[1]["cost"])
    assert math.isnan(stitched.iloc[1]["net_return"])
