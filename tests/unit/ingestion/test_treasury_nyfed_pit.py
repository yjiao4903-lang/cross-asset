from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from cross_asset.ingestion.treasury_nyfed_pit import (
    TreasuryNYFedPITError,
    available_at_for_policy,
    is_us_federal_business_day,
    next_us_federal_business_day,
    nth_us_federal_business_day_of_month,
    parse_date,
    reject_future_available_at,
    us_federal_holidays,
    visible_asof,
)


def test_date_only_available_at_is_end_of_day_et():
    available = available_at_for_policy(
        observation_date=parse_date("2026-09-02"),
        policy="NEXT_CALENDAR_DAY_EOD_ET",
    )
    assert available == datetime(2026, 9, 3, 23, 59, 59, tzinfo=ZoneInfo("America/New_York"))


def test_following_federal_business_day_skips_weekend():
    available = available_at_for_policy(
        observation_date=parse_date("2026-09-04"),
        policy="FOLLOWING_US_FEDERAL_BUSINESS_DAY_1600_ET",
    )
    # 2026-09-04 Friday; 2026-09-07 is Labor Day; next business day is Sep 8 16:00 ET.
    assert available == datetime(2026, 9, 8, 16, 0, 0, tzinfo=ZoneInfo("America/New_York"))


def test_labor_day_2026_is_observed():
    holidays = us_federal_holidays(2026)
    assert date(2026, 9, 7) in holidays
    assert not is_us_federal_business_day(date(2026, 9, 7))
    assert next_us_federal_business_day(date(2026, 9, 4)) == date(2026, 9, 8)


def test_independence_day_saturday_observed_friday():
    # 2026-07-04 is Saturday; OPM observance is Friday 2026-07-03.
    assert date(2026, 7, 3) in us_federal_holidays(2026)
    assert date(2026, 7, 4) not in us_federal_holidays(2026)


def test_thanksgiving_and_juneteenth():
    assert date(2026, 11, 26) in us_federal_holidays(2026)
    assert date(2026, 6, 19) in us_federal_holidays(2026)
    assert date(2020, 6, 19) not in us_federal_holidays(2020)


def test_mspd_fourth_federal_business_day_skips_holiday():
    # January 2026: Jan 1 New Year's Day. First four business days:
    # Jan 2, 5, 6, 7.
    fourth = nth_us_federal_business_day_of_month(2026, 1, 4)
    assert fourth == date(2026, 1, 7)
    available = available_at_for_policy(
        observation_date=parse_date("2025-12-31"),
        policy="FOURTH_BUSINESS_DAY_NEXT_MONTH_EOD_ET",
    )
    assert available == datetime(2026, 1, 7, 23, 59, 59, tzinfo=ZoneInfo("America/New_York"))


def test_last_updated_policy_prefers_official_timestamp():
    available = available_at_for_policy(
        observation_date=parse_date("2026-09-02"),
        policy="LAST_UPDATED_OR_OPERATION_DATE_EOD_ET",
        last_updated="2026-09-02 13:15:00",
    )
    assert available.hour == 13
    assert available.tzinfo is not None


def test_future_available_at_fail_closed():
    available = datetime(2026, 9, 10, 15, 0, tzinfo=ZoneInfo("America/New_York"))
    fetched = datetime(2026, 9, 9, 15, 0, tzinfo=ZoneInfo("America/New_York"))
    with pytest.raises(TreasuryNYFedPITError, match="future_available_at"):
        reject_future_available_at(available, fetched)


def test_visible_asof_drops_unreleased_rows():
    rows = [
        {"available_at": "2026-09-03T23:59:59-04:00", "value": 1},
        {"available_at": "2026-09-08T23:59:59-04:00", "value": 2},
    ]
    visible = visible_asof(rows, "2026-09-04T12:00:00-04:00")
    assert [row["value"] for row in visible] == [1]


def test_visible_asof_requires_available_at():
    with pytest.raises(TreasuryNYFedPITError, match="available_at_required"):
        visible_asof([{"value": 1}], "2026-09-04T12:00:00-04:00")
