import math

import pandas as pd
import pytest

from cross_asset.backtest.metrics import compare_costs
from cross_asset.backtest.returns import (
    AssetReturnSpec,
    portfolio_asset_returns,
    portfolio_period_return,
)
from cross_asset.backtest.walk_forward import (
    build_turnover_cost_ledger,
    cost_sensitivity_ledger,
    drifted_pretrade_weights,
    rebalance_turnover,
)


def test_drifted_pretrade_weights_reproduce_hand_calculation():
    pretrade = drifted_pretrade_weights(
        {"A": 0.5, "B": 0.5},
        {"A": 0.20, "B": 0.0},
    )
    assert pretrade == pytest.approx(
        {"A": 1.2 / 2.2, "B": 1.0 / 2.2}
    )

    resolved, turnover = rebalance_turnover(
        {"A": 0.5, "B": 0.5},
        {"A": 0.5, "B": 0.5},
        {"A": 0.20, "B": 0.0},
        convention="two_sided_notional",
    )
    assert resolved == pytest.approx(pretrade)
    assert turnover == pytest.approx(1.0 / 11.0)

    _, one_way = rebalance_turnover(
        {"A": 0.5, "B": 0.5},
        {"A": 0.5, "B": 0.5},
        {"A": 0.20, "B": 0.0},
        convention="one_way",
    )
    assert one_way == pytest.approx(1.0 / 22.0)


def test_drift_aware_cost_ledger_charges_rebalance_after_asset_move():
    index = pd.date_range("2026-01-02", periods=3, freq="W-FRI")
    gross = pd.Series([0.10, 0.0, float("nan")], index=index)
    targets = pd.DataFrame(
        {"A": [0.5, 0.5, 0.5], "B": [0.5, 0.5, 0.5]},
        index=index,
    )
    asset_returns = pd.DataFrame(
        {"A": [0.20, 0.0, float("nan")], "B": [0.0, 0.0, float("nan")]},
        index=index,
    )

    ledger = build_turnover_cost_ledger(
        gross,
        targets,
        asset_returns=asset_returns,
        cost_bps=10,
    )

    assert ledger.iloc[0]["turnover"] == 0.0
    assert ledger.iloc[1]["turnover"] == pytest.approx(1.0 / 11.0)
    assert ledger.iloc[1]["cost"] == pytest.approx((1.0 / 11.0) * 10 / 10000)
    assert ledger.iloc[1]["turnover_basis"] == "drifted_pretrade_holdings"
    assert ledger.iloc[1]["pretrade_weights"] == pytest.approx(
        {"A": 1.2 / 2.2, "B": 1.0 / 2.2}
    )
    assert ledger.iloc[2]["turnover"] == 0.0
    assert ledger.iloc[2]["turnover_basis"] == "terminal_no_trade"
    assert math.isnan(ledger.iloc[2]["net_return"])
    assert bool(ledger.iloc[1]["drift_aware"]) is True


def test_missing_prior_asset_return_makes_next_cost_unknown():
    gross = pd.Series([0.05, 0.02])
    targets = pd.DataFrame({"A": [0.5, 0.5], "B": [0.5, 0.5]})
    asset_returns = pd.DataFrame({"A": [0.10, 0.0], "B": [float("nan"), 0.0]})

    ledger = build_turnover_cost_ledger(
        gross,
        targets,
        asset_returns=asset_returns,
        cost_bps=10,
    )

    assert ledger.iloc[1]["turnover_basis"] == "drift_unavailable"
    assert math.isnan(ledger.iloc[1]["turnover"])
    assert math.isnan(ledger.iloc[1]["cost"])
    assert math.isnan(ledger.iloc[1]["net_return"])


def test_legacy_target_difference_remains_explicit_when_asset_returns_absent():
    gross = pd.Series([0.01, 0.02])
    targets = pd.DataFrame({"A": [1.0, 0.5], "B": [0.0, 0.5]})

    ledger = build_turnover_cost_ledger(gross, targets, cost_bps=10)

    assert ledger.iloc[1]["turnover"] == pytest.approx(1.0)
    assert ledger.iloc[1]["turnover_basis"] == "target_weights_legacy_fallback"
    assert bool(ledger.iloc[1]["drift_aware"]) is False


def test_cost_sensitivity_and_compare_costs_disclose_drift_basis():
    gross = pd.Series([0.10, 0.0])
    targets = pd.DataFrame({"A": [0.5, 0.5], "B": [0.5, 0.5]})
    asset_returns = pd.DataFrame({"A": [0.20, 0.0], "B": [0.0, 0.0]})

    sensitivity = cost_sensitivity_ledger(
        gross,
        targets,
        asset_returns=asset_returns,
    )
    assert all(bool(item["drift_aware"].iloc[0]) for item in sensitivity.values())
    assert sensitivity[10].iloc[1]["turnover"] == pytest.approx(1.0 / 11.0)

    result = compare_costs(
        gross,
        targets,
        cost_bps=10,
        asset_returns=asset_returns,
    )
    assert result["drift_aware_turnover"] is True
    assert result["turnover_basis"] == "drifted_pretrade_holdings"
    assert result["cost_complete"] is True


def test_portfolio_asset_returns_match_aggregate_return():
    observations = pd.DataFrame(
        [
            {"series_id": "A", "observation_date": "2026-01-02", "value": 100.0},
            {"series_id": "A", "observation_date": "2026-01-09", "value": 120.0},
            {"series_id": "B", "observation_date": "2026-01-02", "value": 100.0},
            {"series_id": "B", "observation_date": "2026-01-09", "value": 100.0},
        ]
    )
    allocation = {"A": 0.5, "B": 0.5}
    specs = {"A": AssetReturnSpec("A"), "B": AssetReturnSpec("B")}

    asset = portfolio_asset_returns(
        observations,
        allocation,
        "2026-01-02",
        "2026-01-09",
        specs=specs,
    )
    aggregate = portfolio_period_return(
        observations,
        allocation,
        "2026-01-02",
        "2026-01-09",
        specs=specs,
    )

    assert asset == pytest.approx({"A": 0.20, "B": 0.0})
    assert aggregate == pytest.approx(0.10)
