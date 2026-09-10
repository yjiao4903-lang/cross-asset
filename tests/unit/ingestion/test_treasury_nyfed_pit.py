from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from cross_asset.ingestion.treasury_nyfed_pit import (
    TreasuryNYFedPITError,
    available_at_for_policy,
    parse_date,
    reject_future_available_at,
    visible_asof,
)


def test_date_only_available_at_is_end_of_day_et():
    available = available_at_for_policy(
        observation_date=parse_date("2026-09-02"),
        policy="NEXT_CALENDAR_DAY_EOD_ET",
    )
    assert available == datetime(2026, 9, 3, 23, 59, 59, tzinfo=ZoneInfo("America/New_York"))


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
