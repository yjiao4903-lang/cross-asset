import numpy as np
import pandas as pd

from .returns import log_return


def annualized_volatility(prices: pd.Series, window: int, annualization: int = 252) -> pd.Series:
    return log_return(prices).rolling(window, min_periods=window).std(ddof=1) * np.sqrt(
        annualization
    )


def volatility_features(
    prices: pd.Series, windows: tuple[int, ...] = (20, 60, 120)
) -> pd.DataFrame:
    return pd.DataFrame({f"vol_{w}d": annualized_volatility(prices, w) for w in windows})
