from __future__ import annotations

import pandas as pd
import pytest

from cross_asset.decision_support.factor_transforms import (
    core_cpi_3m6m_annualized_trend,
    payroll_3m6m_smoothed_momentum,
)


def test_payroll_transform_is_3m6m_smoothed_monthly_job_gain_and_causal():
    dates = pd.date_range("2024-01-01", periods=12, freq="MS")
    levels = pd.Series(
        [
            100000,
            100100,
            100220,
            100360,
            100520,
            100700,
            100900,
            101120,
            101360,
            101620,
            101900,
            102200,
        ],
        index=dates,
        dtype=float,
    )
    baseline = payroll_3m6m_smoothed_momentum(levels)
    changed_future = levels.copy()
    changed_future.iloc[-1] += 10000
    changed = payroll_3m6m_smoothed_momentum(changed_future)

    # Future-only revision cannot alter any already-computable prior timestamp.
    pd.testing.assert_series_equal(baseline.iloc[:-1], changed.iloc[:-1])

    gains = levels.diff()
    expected_last = (gains.iloc[-3:].mean() + gains.iloc[-6:].mean()) / 2.0
    assert baseline.iloc[-1] == pytest.approx(expected_last)


def test_core_cpi_transform_is_3m6m_annualized_not_yoy_and_causal():
    dates = pd.date_range("2024-01-01", periods=18, freq="MS")
    monthly_rates = [
        0.0020,
        0.0022,
        0.0024,
        0.0028,
        0.0031,
        0.0035,
        0.0038,
        0.0034,
        0.0030,
        0.0027,
        0.0025,
        0.0023,
        0.0026,
        0.0030,
        0.0036,
        0.0042,
        0.0045,
    ]
    levels = [300.0]
    for rate in monthly_rates:
        levels.append(levels[-1] * (1.0 + rate))
    values = pd.Series(levels, index=dates)
    trend = core_cpi_3m6m_annualized_trend(values)

    last = values.iloc[-1]
    expected_3m = ((last / values.iloc[-4]) ** 4 - 1.0) * 100.0
    expected_6m = ((last / values.iloc[-7]) ** 2 - 1.0) * 100.0
    expected = (expected_3m + expected_6m) / 2.0
    yoy = (last / values.iloc[-13] - 1.0) * 100.0

    assert trend.iloc[-1] == pytest.approx(expected)
    assert trend.iloc[-1] != pytest.approx(yoy)

    changed_future = values.copy()
    changed_future.iloc[-1] *= 1.5
    changed = core_cpi_3m6m_annualized_trend(changed_future)
    pd.testing.assert_series_equal(trend.iloc[:-1], changed.iloc[:-1])


def test_core_cpi_requires_positive_index_levels():
    values = pd.Series([100.0, 101.0, 0.0, 102.0, 103.0, 104.0, 105.0])
    with pytest.raises(ValueError, match="must be positive"):
        core_cpi_3m6m_annualized_trend(values)
