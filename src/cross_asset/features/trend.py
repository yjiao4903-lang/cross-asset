import pandas as pd

from .returns import period_return


def trend_features(prices: pd.Series, periods: dict[str, int] | None = None) -> pd.DataFrame:
    periods = periods or {"ret_1m": 21, "ret_3m": 63, "ret_6m": 126, "ret_12m": 252}
    return pd.DataFrame({name: period_return(prices, n) for name, n in periods.items()})
