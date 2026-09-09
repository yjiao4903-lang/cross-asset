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
        return datetime.combine(date.fromisoformat(text[:10]), datetime.max.time(), tzinfo=ZoneInfo(timezone))
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=ZoneInfo(timezone))
    return parsed


def end_of_day(value: date, *, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    return datetime(value.year, value.month, value.day, 23, 59, 59, tzinfo=ZoneInfo(timezone))


def add_weekdays(start: date, days: int) -> date:
    cursor = start
    remaining = days
    while remaining > 0:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            remaining -= 1
    return cursor


def first_weekday_of_month(year: int, month: int) -> date:
    cursor = date(year, month, 1)
    while cursor.weekday() >= 5:
        cursor += timedelta(days=1)
    return cursor


def nth_weekday_of_month(year: int, month: int, n: int) -> date:
    cursor = first_weekday_of_month(year, month)
    remaining = n - 1
    while remaining > 0:
        cursor = add_weekdays(cursor, 1)
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
    if policy == "NEXT_BUSINESS_DAY_1500_ET":
        target = add_weekdays(observation_date, 1)
        return datetime(target.year, target.month, target.day, 15, 0, 0, tzinfo=tz)
    if policy == "AUCTION_DATE_EOD_ET":
        return end_of_day(observation_date, timezone=timezone)
    if policy == "FOURTH_BUSINESS_DAY_NEXT_MONTH_EOD_ET":
        year, month = next_month(observation_date)
        return end_of_day(nth_weekday_of_month(year, month, 4), timezone=timezone)
    if policy == "LAST_UPDATED_OR_OPERATION_DATE_EOD_ET":
        if last_updated:
            return parse_datetime(last_updated, timezone=timezone)
        return end_of_day(observation_date, timezone=timezone)
    if policy == "ASOF_PLUS_TWO_CALENDAR_DAYS_EOD_ET":
        return end_of_day(observation_date + timedelta(days=2), timezone=timezone)
    if policy == "ASOF_PLUS_ONE_WEEKDAY_EOD_ET":
        return end_of_day(add_weekdays(observation_date, 1), timezone=timezone)
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
