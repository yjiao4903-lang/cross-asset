from datetime import date

import pytest

from cross_asset.operations.exchange_calendar import (
    CalendarBlockedError,
    CalendarMetadata,
    ExchangeCalendarAdapter,
    weekly_decision_dates,
)


class FakeCalendar:
    def __init__(self, sessions):
        self._sessions = set(sessions)

    def sessions_in_range(self, start, end):
        return [d for d in sorted(self._sessions) if start <= d <= end]


def adapter(cn, hk):
    return ExchangeCalendarAdapter(
        FakeCalendar(cn),
        FakeCalendar(hk),
        metadata=CalendarMetadata("fake", "test", "1", ("XSHG", "XHKG")),
    )


def test_weekend_and_holiday_use_last_common_session():
    cn = {date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 9), date(2025, 1, 10)}
    hk = {date(2025, 1, 6), date(2025, 1, 8), date(2025, 1, 9)}
    assert weekly_decision_dates(date(2025, 1, 4), date(2025, 1, 12), provider=adapter(cn, hk)) == [
        date(2025, 1, 9)
    ]


def test_no_common_day_omits_week():
    p = adapter({date(2025, 1, 6)}, {date(2025, 1, 7)})
    assert weekly_decision_dates(date(2025, 1, 6), date(2025, 1, 12), provider=p) == []


def test_provider_metadata_is_retained():
    p = adapter({date(2025, 1, 6)}, {date(2025, 1, 6)})
    assert p.metadata.source == "test"
    assert p.metadata.calendars == ("XSHG", "XHKG")


def test_missing_provider_is_blocked(monkeypatch):
    from cross_asset.operations import exchange_calendar as mod

    def missing(_name):
        raise ImportError("missing")

    monkeypatch.setattr(mod, "import_module", missing)
    with pytest.raises(CalendarBlockedError, match="BLOCKED"):
        mod.cn_hk_calendar()
