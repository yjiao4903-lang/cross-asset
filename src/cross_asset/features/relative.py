import pandas as pd

from .returns import simple_return


def relative_price(lhs: pd.Series, rhs: pd.Series) -> pd.Series:
    return lhs.astype(float).div(rhs.astype(float)).where(rhs != 0)


def relative_return(lhs: pd.Series, rhs: pd.Series, horizon: int = 1) -> pd.Series:
    return simple_return(relative_price(lhs, rhs), horizon)


def relative_trend(
    lhs: pd.Series, rhs: pd.Series, windows: tuple[int, ...] = (21, 63, 126)
) -> pd.DataFrame:
    rel = relative_price(lhs, rhs)
    return pd.DataFrame({f"relative_ret_{w}d": simple_return(rel, w) for w in windows})
