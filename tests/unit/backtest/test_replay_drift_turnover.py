"""Drift-aware turnover and cost regressions for HistoricalReplay (Issue #19, 19-C2)."""

import math

import pandas as pd
import pytest

from cross_asset.backtest.replay import HistoricalReplay
from cross_asset.backtest.returns import AssetReturnSpec, portfolio_period_return
from cross_asset.backtest.walk_forward import (
    build_turnover_cost_ledger,
    cost_sensitivity_ledger,
)

DAYS = ("2026-01-02", "2026-01-09", "2026-01-16", "2026-01-23")


class ConstantStrategy:
    """Never changes its target: any non-zero turnover must come from drift."""

    def __init__(self, weights=None):
        self.weights = weights or {"A": 0.5, "B": 0.5}
        self.return_specs = {
            asset: AssetReturnSpec(asset) for asset in self.weights
        }

    def __call__(self, _info, _decision):
        return dict(self.weights)

    def realized_return(self, observations, allocation, decision, next_decision):
        return portfolio_period_return(
            observations,
            allocation,
            decision,
            next_decision,
            specs=self.return_specs,
        )


def _observations(prices):
    rows = []
    for index, day in enumerate(DAYS):
        for asset, path in prices.items():
            rows.append(
                {
                    "series_id": asset,
                    "observation_date": day,
                    "available_at": day,
                    "value": path[index],
                }
            )
    return pd.DataFrame(rows)


def _run(prices, **kwargs):
    replay = HistoricalReplay(
        _observations(prices),
        ConstantStrategy(weights=kwargs.pop("weights", None)),
        **kwargs,
    )
    return replay.run(DAYS[0], DAYS[-1])


FLAT = {"A": [100.0] * 4, "B": [100.0] * 4}
A_UP_20 = {"A": [100.0, 100.0, 120.0, 120.0], "B": [100.0] * 4}


def test_drift_hand_calculation_two_sided_and_one_way():
    result = _run(A_UP_20, cost_bps=10)
    # Decision 3 rebalances an unchanged 50/50 target after A returned +20%.
    pretrade = result.pre_trade_weights.iloc[2]
    assert pretrade["A"] == pytest.approx(1.2 / 2.2)
    assert pretrade["B"] == pytest.approx(1.0 / 2.2)
    assert result.turnover.iloc[2] == pytest.approx(1.0 / 11.0)
    assert result.cost.iloc[2] == pytest.approx((1.0 / 11.0) * 10 / 10000)
    assert result.returns.iloc[2] == pytest.approx(-(1.0 / 11.0) * 10 / 10000)

    one_way = _run(A_UP_20, cost_bps=10, turnover_convention="one_way")
    assert one_way.turnover.iloc[2] == pytest.approx(1.0 / 22.0)


def test_unchanged_frozen_target_still_rebalances_after_drift():
    # Same target every decision, yet the unequal asset path forces a real
    # drift rebalance: same target does not mean zero turnover.
    result = _run(A_UP_20, cost_bps=10)
    assert result.turnover.iloc[1] == pytest.approx(0.0)
    assert result.turnover.iloc[2] > 0.0
    assert result.turnover_status.iloc[2] == "drifted_pretrade_holdings"


def test_equal_asset_returns_produce_zero_drift_turnover():
    result = _run(FLAT, cost_bps=10)
    assert (result.turnover.fillna(0.0) == 0.0).all()
    assert result.returns.iloc[1] == pytest.approx(0.0)


def test_negative_return_drift_direction_and_magnitude():
    prices = {"A": [100.0, 100.0, 80.0, 80.0], "B": [100.0] * 4}
    result = _run(prices, cost_bps=10)
    pretrade = result.pre_trade_weights.iloc[2]
    assert pretrade["A"] == pytest.approx(0.8 / 1.8)
    assert pretrade["B"] == pytest.approx(1.0 / 1.8)
    assert result.turnover.iloc[2] == pytest.approx(1.0 / 9.0)


def test_initial_trade_not_charged_by_default():
    result = _run(A_UP_20, cost_bps=100, charge_initial_trade=False)
    assert result.turnover.iloc[0] == 0.0
    assert result.cost.iloc[0] == 0.0
    assert result.turnover_status.iloc[0] == "initial_trade_not_charged"


def test_initial_trade_charged_keeps_existing_convention():
    result = _run(A_UP_20, cost_bps=100, charge_initial_trade=True)
    assert result.turnover.iloc[0] == pytest.approx(1.0)
    assert result.cost.iloc[0] == pytest.approx(1.0 * 100 / 10000)
    assert result.turnover_status.iloc[0] == "initial_target_vs_cash"
    assert result.returns.iloc[0] == pytest.approx(0.0 - 0.01)


def test_missing_nonzero_asset_return_fails_closed():
    prices = {"A": [100.0, 100.0, 120.0, 120.0], "B": [100.0, 100.0]}
    rows = []
    for index, day in enumerate(DAYS):
        for asset, path in prices.items():
            if index >= len(path):
                continue
            rows.append(
                {
                    "series_id": asset,
                    "observation_date": day,
                    "available_at": day,
                    "value": path[index],
                }
            )
    result = HistoricalReplay(
        pd.DataFrame(rows), ConstantStrategy(), cost_bps=10
    ).run(DAYS[0], DAYS[-1])
    # B has no observable level beyond 2026-01-09: its second holding-period
    # return is unknowable, so the next decision's drift and cost are unknown.
    assert result.turnover_status.iloc[2] == "drift_unavailable"
    assert math.isnan(result.turnover.iloc[2])
    assert math.isnan(result.cost.iloc[2])
    assert math.isnan(result.returns.iloc[2])


def test_missing_zero_weight_asset_return_does_not_block_drift():
    prices = {"A": [100.0, 100.0, 120.0, 120.0]}
    rows = []
    for index, day in enumerate(DAYS):
        rows.append(
            {
                "series_id": "A",
                "observation_date": day,
                "available_at": day,
                "value": prices["A"][index],
            }
        )
    result = HistoricalReplay(
        pd.DataFrame(rows),
        ConstantStrategy(weights={"A": 1.0, "B": 0.0, "C": 0.0}),
        cost_bps=10,
    ).run(DAYS[0], DAYS[-1])
    assert result.turnover.iloc[2] == pytest.approx(0.0)
    assert result.turnover_status.iloc[2] == "drifted_pretrade_holdings"


def test_terminal_decision_has_no_trade_and_no_cost():
    result = _run(A_UP_20, cost_bps=100)
    assert result.turnover.iloc[-1] == 0.0
    assert result.cost.iloc[-1] == 0.0
    assert result.turnover_status.iloc[-1] == "terminal_no_trade"
    assert math.isnan(result.returns.iloc[-1])


def test_replay_artifacts_and_records_are_traceable(tmp_path):
    result = _run(A_UP_20, cost_bps=10)
    out = result.write_artifacts(tmp_path)
    names = {path.name for path in out.iterdir()}
    assert {
        "returns.parquet",
        "allocations.parquet",
        "asset_returns.parquet",
        "pre_trade_weights.parquet",
        "turnover_cost.parquet",
    } <= names
    # Row t holds the asset returns for the period decision t -> t+1.
    assert result.asset_returns.loc[DAYS[1], "A"] == pytest.approx(0.20)
    assert result.asset_returns.loc[DAYS[2], "A"] == pytest.approx(0.0)
    assert not result.pre_trade_weights.empty
    assert "turnover measured against drifted pre-trade holdings" in (
        result.assumptions
    )


def test_full_model_decision_records_carry_drift_evidence():
    rows = []
    prices = {"A": [100.0 + 5 * i for i in range(30)], "B": [100.0] * 30}
    for i in range(30):
        day = pd.Timestamp("2026-01-02") + pd.Timedelta(days=i)
        for asset in ("A", "B"):
            rows.append(
                {
                    "series_id": asset,
                    "observation_date": day,
                    "available_at": day,
                    "value": prices[asset][i],
                }
            )
    from cross_asset.backtest.replay import FullModelStrategy

    strategy = FullModelStrategy(["A", "B"])
    result = HistoricalReplay(pd.DataFrame(rows), strategy).run(
        "2026-01-02", "2026-01-23"
    )
    assert result.decisions
    for record in result.decisions:
        assert "turnover_status" in record
        assert "pre_trade_weights" in record
        assert record["turnover"] is None or record["turnover"] >= 0.0


def test_cost_sensitivity_shares_one_drift_turnover_path():
    result = _run(A_UP_20, cost_bps=10)
    sensitivity = cost_sensitivity_ledger(
        result.returns,
        result.allocations,
        asset_returns=result.asset_returns,
        charge_initial_trade=False,
    )
    turnovers = {bps: frame["turnover"] for bps, frame in sensitivity.items()}
    for bps, frame in sensitivity.items():
        pd.testing.assert_series_equal(
            frame["turnover"], turnovers[10], check_names=False
        )
        expected_cost = frame["turnover"] * bps / 10000.0
        pd.testing.assert_series_equal(
            frame["cost"].fillna(-1.0),
            expected_cost.fillna(-1.0),
            check_names=False,
        )


def test_replay_matches_drift_aware_ledger_parity():
    result = _run(A_UP_20, cost_bps=10)
    dates = result.decision_dates
    specs = ConstantStrategy().return_specs
    gross = pd.Series(
        [
            portfolio_period_return(
                _observations(A_UP_20),
                result.allocations.iloc[position],
                dates[position],
                dates[position + 1] if position + 1 < len(dates) else None,
                specs=specs,
            )
            for position in range(len(dates))
        ],
        index=dates,
    )
    ledger = build_turnover_cost_ledger(
        gross,
        result.allocations,
        asset_returns=result.asset_returns,
        cost_bps=10,
        charge_initial_trade=False,
    )
    pd.testing.assert_series_equal(
        ledger["turnover"], result.turnover, check_names=False, check_freq=False
    )
    pd.testing.assert_series_equal(
        ledger["net_return"], result.returns, check_names=False, check_freq=False
    )
    for position in range(len(dates)):
        ledger_pretrade = ledger.iloc[position]["pretrade_weights"]
        replay_pretrade = result.pre_trade_weights.iloc[position]
        if ledger_pretrade is None:
            assert replay_pretrade.isna().all()
            continue
        for asset, value in ledger_pretrade.items():
            assert replay_pretrade[asset] == pytest.approx(value)
