"""Factor-specific DEVELOPMENT_PRIOR transforms for Decision Support v2.

These functions implement the economic definitions frozen in the V2 taxonomy;
they do not decide canonical identity or evidence-lane admission.
"""

from __future__ import annotations

import pandas as pd


def payroll_3m6m_smoothed_momentum(levels: pd.Series) -> pd.Series:
    """3m/6m smoothed payroll momentum from a monthly payroll *level* series.

    Definition: compute monthly payroll changes, then equally combine the
    trailing 3-month and 6-month mean monthly job gains. The output remains in
    the raw payroll change unit and is suitable for subsequent causal
    normalization. No forward fill or future observation is used.
    """

    values = pd.Series(levels, copy=True, dtype=float).dropna().sort_index()
    monthly_change = values.diff()
    smooth_3m = monthly_change.rolling(3, min_periods=3).mean()
    smooth_6m = monthly_change.rolling(6, min_periods=6).mean()
    return ((smooth_3m + smooth_6m) / 2.0).dropna()


def core_cpi_3m6m_annualized_trend(index: pd.Series) -> pd.Series:
    """3m/6m annualized core-CPI trend from a monthly price index.

    Three-month inflation is annualized with exponent 4 and six-month inflation
    with exponent 2; the factor input is their equal-weight average, expressed
    in percentage points. This is a trend lens, not year-over-year inflation.
    """

    values = pd.Series(index, copy=True, dtype=float).dropna().sort_index()
    if (values <= 0).any():
        raise ValueError("core CPI index values must be positive")
    annualized_3m = ((values / values.shift(3)) ** 4 - 1.0) * 100.0
    annualized_6m = ((values / values.shift(6)) ** 2 - 1.0) * 100.0
    return ((annualized_3m + annualized_6m) / 2.0).dropna()


__all__ = [
    "core_cpi_3m6m_annualized_trend",
    "payroll_3m6m_smoothed_momentum",
]
