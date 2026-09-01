import pandas as pd


def correlation_features(
    prices: pd.DataFrame, windows: tuple[int, ...] = (20, 60, 120)
) -> pd.DataFrame:
    r = prices.astype(float).pct_change(fill_method=None)
    out = {}
    for w in windows:
        out[f"corr_{w}d"] = r.rolling(w, min_periods=w).corr().groupby(level=0).mean().mean(axis=1)
    return pd.DataFrame(out, index=prices.index)
