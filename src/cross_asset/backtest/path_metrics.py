"""Shared portfolio-path metrics with explicit NAV baseline semantics."""

from __future__ import annotations

import pandas as pd


def nav_path_from_returns(returns) -> pd.Series:
    """Build a clean NAV path with explicit initial NAV=1.0.

    Missing returns are excluded consistently with the existing performance
    metric contract. The returned path always starts at 1.0; callers that need
    to distinguish an empty return sample should inspect the cleaned input or
    use ``max_drawdown_from_returns``.
    """

    values = pd.Series(returns, dtype=float).dropna().reset_index(drop=True)
    cumulative = (1.0 + values).cumprod()
    return pd.concat(
        [pd.Series([1.0], dtype=float), cumulative],
        ignore_index=True,
    )


def max_drawdown_from_returns(returns) -> float | None:
    """Return maximum drawdown from a NAV path whose initial value is 1.0."""

    values = pd.Series(returns, dtype=float).dropna().reset_index(drop=True)
    if values.empty:
        return None
    nav = nav_path_from_returns(values)
    drawdown = nav / nav.cummax() - 1.0
    return float(drawdown.min())


__all__ = ["max_drawdown_from_returns", "nav_path_from_returns"]
