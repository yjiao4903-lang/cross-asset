import pandas as pd
import pytest

from cross_asset.backtest.replay import HistoricalReplay
from cross_asset.backtest.returns import AssetReturnSpec


class _DriftStrategy:
    return_specs = {
        "A": AssetReturnSpec("A", kind="price"),
        "B": AssetReturnSpec("B", kind="price"),
    }

    def __init__(self):
        self.last_scores = {}
        self.last_decision = None

    def __call__(self, _info, decision):
        self.last_decision = {
            "asset_scores": {},
            "attribution": {},
            "signal_components": {},
            "model_versions": {"test": "drift_v1"},
            "data_cutoff": decision,
            "missing_signal_assets": [],
        }
        return {"A": 0.5, "B": 0.5}


def _observations():
    rows = []
    levels = {
        "2026-01-02": {"A": 100.0, "B": 100.0},
        "2026-01-09": {"A": 120.0, "B": 100.0},
        "2026-01-16": {"A": 120.0, "B": 100.0},
    }
    for day, values in levels.items():
        for series_id, value in values.items():
            rows.append(
                {
                    "series_id": series_id,
                    "observation_date": day,
                    "available_at": day,
                    "value": value,
                }
            )
    return pd.DataFrame(rows)


def test_historical_replay_rebalances_from_drifted_holdings():
    result = HistoricalReplay(
        _observations(),
        _DriftStrategy(),
        cost_bps=10,
        turnover_convention="two_sided_notional",
        charge_initial_trade=False,
    ).run("2026-01-02", "2026-01-16")

    assert result.returns.iloc[0] == pytest.approx(0.10)
    assert result.returns.iloc[1] == pytest.approx(-(1.0 / 11.0) * 10 / 10000)
    assert pd.isna(result.returns.iloc[2])

    first, second, terminal = result.decisions
    assert first["turnover"] == 0.0
    assert first["turnover_basis"] == "initial_trade_not_charged"
    assert first["asset_returns"] == pytest.approx({"A": 0.20, "B": 0.0})

    assert second["pretrade_weights"] == pytest.approx(
        {"A": 1.2 / 2.2, "B": 1.0 / 2.2}
    )
    assert second["turnover"] == pytest.approx(1.0 / 11.0)
    assert second["turnover_basis"] == "drifted_pretrade_holdings"
    assert second["cost"] == pytest.approx((1.0 / 11.0) * 10 / 10000)
    assert second["gross_return"] == pytest.approx(0.0)
    assert second["net_return"] == pytest.approx(result.returns.iloc[1])

    assert terminal["turnover"] == 0.0
    assert terminal["turnover_basis"] == "terminal_no_trade"
    assert terminal["pretrade_weights"] is None
    assert terminal["asset_returns"] is None
    assert pd.isna(terminal["net_return"])


def test_historical_replay_fails_closed_when_prior_asset_return_is_missing():
    observations = _observations()
    observations = observations[
        ~(
            (observations["series_id"] == "A")
            & (observations["observation_date"] == "2026-01-09")
        )
    ]

    result = HistoricalReplay(
        observations,
        _DriftStrategy(),
        cost_bps=10,
    ).run("2026-01-02", "2026-01-16")

    assert pd.isna(result.returns.iloc[0])
    assert pd.isna(result.returns.iloc[1])
    assert result.decisions[1]["turnover_basis"] == "drift_unavailable"
    assert pd.isna(result.decisions[1]["turnover"])
    assert pd.isna(result.decisions[1]["cost"])
    assert pd.isna(result.decisions[1]["net_return"])


def test_historical_replay_preserves_explicit_initial_trade_cost():
    result = HistoricalReplay(
        _observations(),
        _DriftStrategy(),
        cost_bps=100,
        charge_initial_trade=True,
    ).run("2026-01-02", "2026-01-16")

    assert result.decisions[0]["turnover"] == pytest.approx(1.0)
    assert result.decisions[0]["turnover_basis"] == "initial_target_vs_cash"
    assert result.returns.iloc[0] == pytest.approx(0.09)
