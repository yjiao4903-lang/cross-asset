"""Conservative available_at / as-of filters for Treasury and NY Fed C0."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .treasury_nyfed_c0_contract import DEFAULT_TIMEZONE


class TreasuryNYFedPITError(ValueError):
    """Fail-closed PIT / future-leakage errors."""


def parse_date(value: str | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def parse_datetime(value: str | datetime, *, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=ZoneInfo(timezone))
        return value
    text = str(value).strip().replace("Z", "+00:00")
    if "T" not in text and " " in text:
        text = text.replace(" ", "T", 1)
    if "T" not in text:
        return datetime.combine(
            date.fromisoformat(text[:10]),
            datetime.max.time(),
            tzinfo=ZoneInfo(timezone),
        )
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=ZoneInfo(timezone))
    return parsed


def end_of_day(value: date, *, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    return datetime(value.year, value.month, value.day, 23, 59, 59, tzinfo=ZoneInfo(timezone))


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    cursor = date(year, month, 1)
    while cursor.weekday() != weekday:
        cursor += timedelta(days=1)
    return cursor + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        cursor = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        cursor = date(year, month + 1, 1) - timedelta(days=1)
    while cursor.weekday() != weekday:
        cursor -= timedelta(days=1)
    return cursor


def _observed_holiday(value: date) -> date:
    if value.weekday() == 5:
        return value - timedelta(days=1)
    if value.weekday() == 6:
        return value + timedelta(days=1)
    return value


def us_federal_holidays(year: int) -> frozenset[date]:
    """OPM-style nationwide U.S. federal holidays, including Saturday/Sunday observance.

    Isolated C0 calendar. Does not reuse Wind or other workstream calendars.
    Inauguration Day is omitted because it is not a nationwide closing day.
    Juneteenth is included from 2021 onward.
    """

    fixed = [
        date(year, 1, 1),
        date(year, 7, 4),
        date(year, 11, 11),
        date(year, 12, 25),
    ]
    if year >= 2021:
        fixed.append(date(year, 6, 19))
    holidays = {_observed_holiday(item) for item in fixed}
    holidays.add(_nth_weekday(year, 1, 0, 3))
    holidays.add(_nth_weekday(year, 2, 0, 3))
    holidays.add(_last_weekday(year, 5, 0))
    holidays.add(_nth_weekday(year, 9, 0, 1))
    holidays.add(_nth_weekday(year, 10, 0, 2))
    holidays.add(_nth_weekday(year, 11, 3, 4))
    return frozenset(holidays)


def is_us_federal_business_day(value: date) -> bool:
    if value.weekday() >= 5:
        return False
    return value not in us_federal_holidays(value.year)


def add_us_federal_business_days(start: date, days: int) -> date:
    if days < 0:
        raise TreasuryNYFedPITError("business_day_delta_must_be_non_negative")
    cursor = start
    remaining = days
    while remaining > 0:
        cursor += timedelta(days=1)
        if is_us_federal_business_day(cursor):
            remaining -= 1
    return cursor


def next_us_federal_business_day(value: date) -> date:
    return add_us_federal_business_days(value, 1)


def first_us_federal_business_day_of_month(year: int, month: int) -> date:
    cursor = date(year, month, 1) - timedelta(days=1)
    return next_us_federal_business_day(cursor)


def nth_us_federal_business_day_of_month(year: int, month: int, n: int) -> date:
    if n < 1:
        raise TreasuryNYFedPITError("business_day_n_must_be_positive")
    first = first_us_federal_business_day_of_month(year, month)
    if n == 1:
        return first
    return add_us_federal_business_days(first, n - 1)


def add_weekdays(start: date, days: int) -> date:
    cursor = start
    remaining = days
    while remaining > 0:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            remaining -= 1
    return cursor


def next_month(value: date) -> tuple[int, int]:
    if value.month == 12:
        return value.year + 1, 1
    return value.year, value.month + 1


def available_at_for_policy(
    *,
    observation_date: date,
    policy: str,
    last_updated: str | datetime | None = None,
    timezone: str = DEFAULT_TIMEZONE,
) -> datetime:
    tz = ZoneInfo(timezone)
    if policy == "NEXT_CALENDAR_DAY_EOD_ET":
        return end_of_day(observation_date + timedelta(days=1), timezone=timezone)
    if policy in {
        "FOLLOWING_US_FEDERAL_BUSINESS_DAY_1600_ET",
        "NEXT_BUSINESS_DAY_1600_ET",
        "NEXT_BUSINESS_DAY_1500_ET",
    }:
        target = next_us_federal_business_day(observation_date)
        hour = 15 if policy == "NEXT_BUSINESS_DAY_1500_ET" else 16
        return datetime(target.year, target.month, target.day, hour, 0, 0, tzinfo=tz)
    if policy == "AUCTION_DATE_EOD_ET":
        return end_of_day(observation_date, timezone=timezone)
    if policy == "FOURTH_BUSINESS_DAY_NEXT_MONTH_EOD_ET":
        year, month = next_month(observation_date)
        fourth = nth_us_federal_business_day_of_month(year, month, 4)
        return end_of_day(fourth, timezone=timezone)
    if policy == "LAST_UPDATED_OR_OPERATION_DATE_EOD_ET":
        if last_updated:
            return parse_datetime(last_updated, timezone=timezone)
        return end_of_day(observation_date, timezone=timezone)
    if policy == "ASOF_PLUS_TWO_CALENDAR_DAYS_EOD_ET":
        return end_of_day(observation_date + timedelta(days=2), timezone=timezone)
    if policy == "ASOF_PLUS_ONE_WEEKDAY_EOD_ET":
        return end_of_day(next_us_federal_business_day(observation_date), timezone=timezone)
    raise TreasuryNYFedPITError(f"unknown_available_at_policy:{policy}")


def ensure_timezone(value: datetime, *, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TreasuryNYFedPITError("timezone_required")
    return value.astimezone(ZoneInfo(timezone))


def reject_future_available_at(available_at: datetime, fetched_at: datetime) -> None:
    available = ensure_timezone(available_at)
    fetched = ensure_timezone(fetched_at)
    if available > fetched:
        raise TreasuryNYFedPITError(
            f"future_available_at:{available.isoformat()}:{fetched.isoformat()}"
        )


def visible_asof(
    rows: list[dict[str, object]],
    decision_time: str | datetime,
    *,
    available_at_field: str = "available_at",
) -> list[dict[str, object]]:
    cutoff = parse_datetime(decision_time)
    visible: list[dict[str, object]] = []
    for row in rows:
        raw = row.get(available_at_field)
        if raw is None:
            raise TreasuryNYFedPITError("available_at_required")
        available = parse_datetime(str(raw) if not isinstance(raw, datetime) else raw)
        if available <= cutoff:
            visible.append(row)
    return visible
