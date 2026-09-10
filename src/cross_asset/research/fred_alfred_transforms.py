"""Vintage-aware, research-only transforms for C0 FRED/ALFRED staging records."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from cross_asset.ingestion.fred_alfred_pit import VintageObservation, snapshot_asof


def causal_series(
    records: Iterable[VintageObservation],
    *,
    decision_time,
) -> pd.Series:
    rows = snapshot_asof(records, decision_time)
    values = {
        pd.Timestamp(row.observation_date): float(row.value)
        for row in rows
        if row.value is not None
    }
    return pd.Series(values, dtype=float).sort_index()


def yoy(
    records: Iterable[VintageObservation],
    *,
    decision_time,
    periods: int = 12,
) -> pd.Series:
    series = causal_series(records, decision_time=decision_time)
    return series.pct_change(periods=periods, fill_method=None)


def mom(
    records: Iterable[VintageObservation],
    *,
    decision_time,
) -> pd.Series:
    series = causal_series(records, decision_time=decision_time)
    return series.pct_change(periods=1, fill_method=None)


def annualized_mom(
    records: Iterable[VintageObservation],
    *,
    decision_time,
    periods_per_year: int = 12,
) -> pd.Series:
    changes = mom(records, decision_time=decision_time)
    return (1.0 + changes).pow(periods_per_year) - 1.0


def spread(
    left: Iterable[VintageObservation],
    right: Iterable[VintageObservation],
    *,
    decision_time,
) -> pd.Series:
    lhs = causal_series(left, decision_time=decision_time)
    rhs = causal_series(right, decision_time=decision_time)
    aligned = pd.concat([lhs.rename("left"), rhs.rename("right")], axis=1).dropna()
    return aligned["left"] - aligned["right"]


def rolling_zscore(
    records: Iterable[VintageObservation],
    *,
    decision_time,
    window: int,
    min_periods: int | None = None,
) -> pd.Series:
    if window < 2:
        raise ValueError("rolling_zscore_window_must_be_at_least_two")
    min_periods = min_periods or window
    series = causal_series(records, decision_time=decision_time)
    mean = series.rolling(window, min_periods=min_periods).mean()
    std = series.rolling(window, min_periods=min_periods).std(ddof=0)
    result = (series - mean) / std.replace(0.0, np.nan)
    return result


def _last_percentile(values: np.ndarray) -> float:
    if len(values) == 0 or np.isnan(values[-1]):
        return np.nan
    valid = values[~np.isnan(values)]
    if not len(valid):
        return np.nan
    return float((valid <= values[-1]).sum() / len(valid))


def rolling_percentile(
    records: Iterable[VintageObservation],
    *,
    decision_time,
    window: int,
    min_periods: int | None = None,
) -> pd.Series:
    if window < 2:
        raise ValueError("rolling_percentile_window_must_be_at_least_two")
    min_periods = min_periods or window
    series = causal_series(records, decision_time=decision_time)
    return series.rolling(window, min_periods=min_periods).apply(
        _last_percentile,
        raw=True,
    )


__all__ = [
    "annualized_mom",
    "causal_series",
    "mom",
    "rolling_percentile",
    "rolling_zscore",
    "spread",
    "yoy",
]
