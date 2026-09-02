"""Causal signal normalization utilities.

All baselines use observations strictly prior to the value being scored. The
caller is responsible for supplying a point-in-time clipped series.
"""

from __future__ import annotations

import pandas as pd


def causal_zscore(
    series: pd.Series,
    *,
    min_history: int = 20,
    window: int | None = None,
    clip: float | None = 2.0,
) -> pd.Series:
    """Normalize each value against only its previously observed history."""

    if min_history < 2:
        raise ValueError("min_history must be at least two")
    if window is not None and window < min_history:
        raise ValueError("window must be greater than or equal to min_history")
    if clip is not None and clip <= 0:
        raise ValueError("clip must be positive")

    values = pd.Series(series, copy=True, dtype=float)
    prior = values.shift(1)
    if window is None:
        mean = prior.expanding(min_periods=min_history).mean()
        std = prior.expanding(min_periods=min_history).std(ddof=1)
    else:
        mean = prior.rolling(window, min_periods=min_history).mean()
        std = prior.rolling(window, min_periods=min_history).std(ddof=1)

    score = (values - mean) / std
    flat = std.eq(0) & values.notna() & mean.notna()
    score = score.mask(flat, 0.0)
    if clip is not None:
        score = score.clip(-float(clip), float(clip))
    return score


def latest_causal_zscore(
    series: pd.Series,
    *,
    min_history: int = 20,
    window: int | None = None,
    clip: float | None = 2.0,
) -> float | None:
    """Return the latest available causal z-score, or None when history is insufficient."""

    scores = causal_zscore(
        series,
        min_history=min_history,
        window=window,
        clip=clip,
    )
    if scores.empty or pd.isna(scores.iloc[-1]):
        return None
    return float(scores.iloc[-1])


def bounded_score(value, *, clip: float = 2.0) -> float | None:
    if value is None or pd.isna(value):
        return None
    if clip <= 0:
        raise ValueError("clip must be positive")
    return max(-clip, min(clip, float(value)))


__all__ = ["bounded_score", "causal_zscore", "latest_causal_zscore"]
