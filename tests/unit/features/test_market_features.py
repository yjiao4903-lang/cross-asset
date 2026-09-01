import numpy as np
import pandas as pd

from cross_asset.features.drawdown import drawdown_features
from cross_asset.features.relative import relative_price
from cross_asset.features.returns import log_return, simple_return
from cross_asset.features.trend import trend_features
from cross_asset.features.volatility import volatility_features


def test_returns_and_log_return():
    p = pd.Series([100.0, 110.0])
    assert np.isclose(simple_return(p).iloc[-1], 0.1)
    assert np.isclose(log_return(p).iloc[-1], np.log(1.1))


def test_short_history_is_unavailable():
    p = pd.Series(np.arange(10.0) + 1)
    assert trend_features(p)["ret_1m"].isna().all()
    assert volatility_features(p)["vol_20d"].isna().all()


def test_drawdown_and_relative_missing_are_not_zero():
    p = pd.Series([100.0, 120.0, 90.0])
    d = drawdown_features(p, windows=(2,))
    assert d.current_drawdown.iloc[-1] < 0
    assert relative_price(p, p * 0).isna().all()
