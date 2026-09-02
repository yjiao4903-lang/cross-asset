from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt

import numpy as np
import pandas as pd

from .normalization import bounded_score
from .returns import log_return, period_return

DEFAULT_TREND_PERIODS = {
    "ret_1m": 21,
    "ret_3m": 63,
    "ret_6m": 126,
    "ret_12m": 252,
}


@dataclass(frozen=True)
class TrendSignal:
    score: float | None
    confidence: float
    components: dict[str, float | None] = field(default_factory=dict)
    raw_returns: dict[str, float | None] = field(default_factory=dict)
    model_version: str = "trend_signal_v0.2"


def trend_features(
    prices: pd.Series, periods: dict[str, int] | None = None
) -> pd.DataFrame:
    periods = periods or DEFAULT_TREND_PERIODS
    return pd.DataFrame({name: period_return(prices, n) for name, n in periods.items()})


def multi_horizon_trend_signal(
    prices: pd.Series,
    *,
    periods: dict[str, int] | None = None,
    weights: dict[str, float] | None = None,
    direction: float = 1.0,
    clip: float = 2.0,
) -> TrendSignal:
    """Build a dimensionless multi-horizon trend signal.

    Each horizon is expressed as its log price move divided by the realized
    standard deviation of daily log returns over the same horizon. This makes
    1M/3M/6M/12M moves comparable without fitting a cross-asset scaler.
    """

    horizons = periods or DEFAULT_TREND_PERIODS
    if not horizons:
        raise ValueError("at least one trend horizon is required")
    if any(int(n) < 2 for n in horizons.values()):
        raise ValueError("trend horizons must be at least two observations")
    configured_weights = weights or {name: 1.0 for name in horizons}
    if set(configured_weights) != set(horizons):
        raise ValueError("trend weights must match trend period names")
    if any(float(weight) <= 0 for weight in configured_weights.values()):
        raise ValueError("trend weights must be positive")

    values = pd.Series(prices, copy=True, dtype=float).dropna()
    if not values.index.is_monotonic_increasing:
        values = values.sort_index()
    daily = log_return(values)

    components: dict[str, float | None] = {}
    raw_returns: dict[str, float | None] = {}
    for name, horizon in horizons.items():
        horizon = int(horizon)
        if len(values) <= horizon:
            components[name] = None
            raw_returns[name] = None
            continue

        start = float(values.iloc[-horizon - 1])
        end = float(values.iloc[-1])
        if start <= 0 or end <= 0:
            components[name] = None
            raw_returns[name] = None
            continue

        raw_returns[name] = end / start - 1.0
        move = np.log(end / start)
        trailing = daily.iloc[-horizon:].dropna()
        sigma = float(trailing.std(ddof=1)) * sqrt(horizon) if len(trailing) >= 2 else float("nan")
        if not np.isfinite(sigma):
            components[name] = None
        elif sigma == 0:
            components[name] = 0.0 if move == 0 else float(np.sign(move) * clip * direction)
        else:
            components[name] = bounded_score(direction * move / sigma, clip=clip)

    available = {name: value for name, value in components.items() if value is not None}
    total_weight = sum(float(configured_weights[name]) for name in horizons)
    available_weight = sum(float(configured_weights[name]) for name in available)
    if not available:
        return TrendSignal(None, 0.0, components, raw_returns)

    score = sum(
        float(available[name]) * float(configured_weights[name])
        for name in available
    ) / available_weight
    return TrendSignal(
        bounded_score(score, clip=clip),
        available_weight / total_weight,
        components,
        raw_returns,
    )


__all__ = [
    "DEFAULT_TREND_PERIODS",
    "TrendSignal",
    "multi_horizon_trend_signal",
    "trend_features",
]
