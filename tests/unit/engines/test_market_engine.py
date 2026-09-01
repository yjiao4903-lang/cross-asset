import numpy as np
import pandas as pd

from cross_asset.engines.market import MarketEngine


def test_market_engine_marks_short_series_unavailable():
    state = MarketEngine(min_history=21).build(
        {"US_EQ": pd.Series(np.arange(5.0) + 1)}, as_of="2025-01-01"
    )
    assert state.assets == {}
    assert state.unavailable == ["US_EQ"]


def test_market_engine_emits_versioned_state():
    state = MarketEngine().build({"US_EQ": pd.Series(np.arange(300.0) + 1)}, as_of="2025-01-01")
    assert state.model_version == "market_v0.1" and state.assets["US_EQ"]["available"] is True
