import numpy as np
import pandas as pd


def simple_return(prices: pd.Series, periods: int = 1) -> pd.Series:
    return prices.astype(float).pct_change(periods=periods, fill_method=None)


def log_return(prices: pd.Series, periods: int = 1) -> pd.Series:
    p = prices.astype(float)
    return np.log(p / p.shift(periods)).replace([np.inf, -np.inf], np.nan)


def period_return(prices: pd.Series, periods: int) -> pd.Series:
    if periods < 1:
        raise ValueError("periods must be positive")
    return simple_return(prices, periods)
