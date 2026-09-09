from datetime import date

import pytest

from cross_asset.features.macro import transform_series


def test_pct_change_12m_uses_matching_observation_date():
    rows = [
        {"observation_date": date(2024, 1, 1), "value": 200},
        {"observation_date": date(2024, 2, 1), "value": None},
        {"observation_date": date(2025, 1, 1), "value": 220},
        {"observation_date": date(2025, 2, 1), "value": 230},
    ]
    assert transform_series([rows[0], rows[2]], {"type": "pct_change_12m"}).value == pytest.approx(10.0)
    missing = transform_series(rows[:1] + rows[1:2] + rows[3:4], {"type": "pct_change_12m"})
    assert not missing.available and missing.reason == "missing_lag_period"


def test_change_in_yoy_pp_is_percentage_points():
    rows = [
        {"observation_date": date(2024, 1, 1), "value": 2.0},
        {"observation_date": date(2025, 1, 1), "value": 3.5},
    ]
    result = transform_series(rows, {"type": "change_in_yoy_pp"})
    assert result.available and result.value == 1.5


def test_month_end_and_missing_current_period_fail_closed():
    rows = [
        {"observation_date": date(2024, 2, 29), "value": 200},
        {"observation_date": date(2025, 2, 28), "value": 220},
    ]
    result = transform_series(rows, {"type": "pct_change_12m", "period": "month"})
    assert result.available and result.value == pytest.approx(10.0)
    missing_month = transform_series(
        [{"observation_date": date(2024, 1, 31), "value": 200},
         {"observation_date": date(2025, 2, 28), "value": 220}],
        {"type": "pct_change_12m", "period": "month"},
    )
    assert not missing_month.available and missing_month.reason == "missing_lag_period"
    current_missing = transform_series(
        [{"observation_date": date(2024, 1, 31), "value": 200},
         {"observation_date": date(2025, 1, 31), "value": None}],
        {"type": "pct_change_12m"},
    )
    assert not current_missing.available and current_missing.reason == "missing_lag_period"
