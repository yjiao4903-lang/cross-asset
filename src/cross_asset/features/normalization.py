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
    """Normalize each value against only its previously observed history.

    A zero-variance prior history is not a valid neutral z-score. If the current
    value exactly continues the flat history, the 0/0 result remains unavailable
    (NaN). If the current value jumps away from that flat history, its standardized
    deviation is directionally unbounded and is therefore represented as +/-inf
    before applying the caller's existing clip policy. This distinguishes a flat
    continuation from a genuine zero-variance anomaly without inventing a new
    tuning threshold.
    """

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
    flat_continuation = flat & values.eq(mean)
    flat_jump_up = flat & values.gt(mean)
    flat_jump_down = flat & values.lt(mean)
    score = score.mask(flat_continuation)
    score = score.mask(flat_jump_up, float("inf"))
    score = score.mask(flat_jump_down, float("-inf"))
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
    """Return the latest available causal z-score, or None when unavailable."""

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
