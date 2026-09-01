import pandas as pd


def drawdown_features(prices: pd.Series, windows: tuple[int, ...] = (252,)) -> pd.DataFrame:
    p = prices.astype(float)
    peak = p.cummax()
    dd = p / peak - 1
    out = pd.DataFrame({"rolling_peak": peak, "current_drawdown": dd})
    for w in windows:
        high = p.rolling(w, min_periods=w).max()
        out[f"high_distance_{w}d"] = p / high - 1
        out[f"max_drawdown_{w}d"] = dd.rolling(w, min_periods=w).min()
    return out
