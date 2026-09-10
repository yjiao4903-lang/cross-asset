from datetime import date
from pathlib import Path

import pytest
import yaml

from cross_asset.features.macro import transform_series, transform_unit_semantics


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

    units = transform_unit_semantics(
        {
            "raw_unit": "percent_yoy",
            "derived_unit": "percentage_points",
            "transform": {"type": "change_in_yoy_pp", "period": "month"},
        }
    )
    assert units.resolved
    assert units.raw_unit == "percent_yoy"
    assert units.derived_unit == "percentage_points"


def test_month_end_and_missing_current_period_fail_closed():
    rows = [
        {"observation_date": date(2024, 2, 29), "value": 200},
        {"observation_date": date(2025, 2, 28), "value": 220},
    ]
    result = transform_series(rows, {"type": "pct_change_12m", "period": "month"})
    assert result.available and result.value == pytest.approx(10.0)
    missing_month = transform_series(
        [
            {"observation_date": date(2024, 1, 31), "value": 200},
            {"observation_date": date(2025, 2, 28), "value": 220},
        ],
        {"type": "pct_change_12m", "period": "month"},
    )
    assert not missing_month.available and missing_month.reason == "missing_lag_period"
    current_missing = transform_series(
        [
            {"observation_date": date(2024, 1, 31), "value": 200},
            {"observation_date": date(2025, 1, 31), "value": None},
        ],
        {"type": "pct_change_12m"},
    )
    assert not current_missing.available and current_missing.reason == "missing_lag_period"


def test_quarter_lag_uses_exact_calendar_quarter_not_row_position():
    rows = [
        {"observation_date": date(2024, 3, 31), "value": 100.0},
        {"observation_date": date(2024, 9, 30), "value": 110.0},
        {"observation_date": date(2025, 3, 31), "value": 125.0},
    ]
    result = transform_series(
        rows,
        {"type": "difference_12m", "period": "quarter", "lag_months": 12},
    )
    assert result.available and result.value == 25.0

    missing_target = transform_series(
        rows[1:],
        {"type": "difference_12m", "period": "quarter", "lag_months": 12},
    )
    assert not missing_target.available
    assert missing_target.reason == "missing_lag_period"


def test_formal_macro_config_has_explicit_raw_and_derived_units():
    config = yaml.safe_load(Path("config/macro.yml").read_text(encoding="utf-8"))
    series = config["series"]

    level = transform_unit_semantics(series["US_UNEMPLOYMENT"])
    assert level.resolved
    assert level.transform_type == "level"
    assert level.raw_unit == "percent"
    assert level.derived_unit == "percent"

    yoy = transform_unit_semantics(series["US_CPI"])
    assert yoy.resolved
    assert yoy.transform_type == "pct_change_12m"
    assert yoy.raw_unit == "index"
    assert yoy.derived_unit == "percent_yoy"

    for series_id, definition in series.items():
        units = transform_unit_semantics(definition)
        assert definition["unit"] == definition["derived_unit"]
        if definition["transform"]["type"] == "ambiguous_raw_semantics":
            assert not units.resolved
            assert units.reason == "ambiguous_raw_semantics"
            assert units.raw_unit == "UNRESOLVED"
            assert units.derived_unit == "UNRESOLVED"
        else:
            assert units.resolved, series_id


def test_direct_zscore_flat_continuation_is_not_valid_neutral():
    result = transform_series(
        [{"value": 5.0}, {"value": 5.0}, {"value": 5.0}],
        {"type": "zscore"},
    )
    assert not result.available
    assert result.value is None
    assert result.reason == "zero_variance_continuation"
