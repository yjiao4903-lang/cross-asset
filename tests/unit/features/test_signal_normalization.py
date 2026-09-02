import numpy as np
import pandas as pd
import pytest

from cross_asset.backtest.returns import AssetReturnSpec, return_index_from_series
from cross_asset.engines.market import MarketEngine
from cross_asset.features.normalization import causal_zscore, latest_causal_zscore
from cross_asset.features.trend import multi_horizon_trend_signal


def test_causal_zscore_is_invariant_to_future_append():
    base = pd.Series(np.arange(1.0, 41.0), index=pd.date_range("2025-01-01", periods=40))
    before = causal_zscore(base, min_history=10)
    extended = pd.concat(
        [
            base,
            pd.Series(
                [9999.0],
                index=[pd.Timestamp("2025-02-10")],
            ),
        ]
    )
    after = causal_zscore(extended, min_history=10)
    pd.testing.assert_series_equal(before, after.iloc[: len(before)], check_names=False)


def test_flat_history_normalizes_to_zero_after_minimum_history():
    series = pd.Series([5.0] * 30)
    assert latest_causal_zscore(series, min_history=10) == 0.0


def test_multi_horizon_trend_is_dimensionless_and_missing_aware():
    index = pd.date_range("2024-01-01", periods=300)
    prices = pd.Series(np.exp(np.linspace(0, 0.3, 300)), index=index)
    signal = multi_horizon_trend_signal(prices)
    assert signal.score is not None and 0 < signal.score <= 2
    assert signal.confidence == pytest.approx(1.0)
    assert set(signal.components) == {"ret_1m", "ret_3m", "ret_6m", "ret_12m"}

    short = multi_horizon_trend_signal(prices.iloc[:30])
    assert short.score is not None
    assert short.confidence == pytest.approx(0.25)


def test_yield_proxy_becomes_price_like_return_index():
    yields = pd.Series(
        [3.0, 2.95, 2.90],
        index=pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]),
    )
    index = return_index_from_series(
        yields,
        AssetReturnSpec(
            "CN10Y",
            "yield_duration_proxy",
            duration_years=8.0,
            yield_scale=100.0,
        ),
    )
    assert index.iloc[-1] > index.iloc[0]


def test_market_engine_emits_normalized_trend_and_risk_contracts():
    rng = np.random.default_rng(7)
    returns = np.r_[rng.normal(0.0005, 0.002, 220), rng.normal(0.0005, 0.02, 80)]
    prices = pd.Series(
        100 * np.exp(np.cumsum(returns)),
        index=pd.date_range("2025-01-01", periods=len(returns)),
    )
    state = MarketEngine(risk_min_history=40).build({"A": prices})
    signals = state.assets["A"]["signals"]
    assert signals["trend"]["model_version"] == "trend_signal_v0.2"
    assert signals["risk"]["model_version"] == "risk_signal_v0.2"
    assert signals["risk"]["score"] is not None
    assert -2 <= signals["risk"]["score"] <= 2
