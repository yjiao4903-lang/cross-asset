import pandas as pd


def winsorize(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    if not 0 <= lower < upper <= 1:
        raise ValueError("invalid quantiles")
    return series.clip(series.quantile(lower), series.quantile(upper))
