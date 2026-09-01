"""Optional exchange-calendar integration for CN/HK weekly decisions.

The project deliberately has no calendar dependency in its base installation.  This
module therefore accepts calendar objects by injection and only imports a provider
when a caller explicitly asks for one.  A missing provider is a hard BLOCKED state;
there is no weekday approximation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import Any


class CalendarBlockedError(RuntimeError):
    """Calendar dates cannot be established with the requested provider."""

    status = "BLOCKED"


@dataclass(frozen=True)
class CalendarMetadata:
    provider: str
    source: str
    source_version: str
    calendars: tuple[str, ...]
    status: str = "VERIFIED"


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "UNKNOWN"


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    # pandas Timestamp and numpy datetime64 both stringify usefully here.
    return date.fromisoformat(str(value)[:10])


class ExchangeCalendarAdapter:
    """Small common interface around exchange_calendars/PMC or test fakes."""

    def __init__(self, cn: Any, hk: Any, *, metadata: CalendarMetadata):
        self._calendars = {"XSHG": cn, "XHKG": hk}
        self.metadata = metadata

    def sessions(self, market: str, start: date, end: date) -> set[date]:
        calendar = self._calendars[market]
        if hasattr(calendar, "sessions_in_range"):
            values = calendar.sessions_in_range(start, end)
        elif hasattr(calendar, "schedule"):
            values = calendar.schedule(start_date=start, end_date=end).index
        elif hasattr(calendar, "sessions"):
            values = calendar.sessions(start, end)
        else:
            raise TypeError(f"calendar {market} has no sessions API")
        return {_as_date(v) for v in values}

    def common_sessions(self, start: date, end: date) -> set[date]:
        return self.sessions("XSHG", start, end) & self.sessions("XHKG", start, end)

    def weekly_decision_dates(self, start: date, end: date) -> list[date]:
        if end < start:
            return []
        common = self.common_sessions(start, end)
        # ISO week grouping makes the result stable across provider datetime types.
        return [max(days) for _, days in sorted(_group_by_week(common).items())]


def _group_by_week(days: Iterable[date]) -> dict[tuple[int, int], list[date]]:
    result: dict[tuple[int, int], list[date]] = {}
    for day in days:
        iso = day.isocalendar()
        result.setdefault((iso.year, iso.week), []).append(day)
    return result


def _load_exchange_calendars() -> ExchangeCalendarAdapter:
    try:
        module = import_module("exchange_calendars")
    except ImportError as exc:
        raise CalendarBlockedError(
            "BLOCKED: exchange_calendars is unavailable; install it in the deployment environment "
            "or inject calendars explicitly (no Mon-Fri fallback)."
        ) from exc
    try:
        return ExchangeCalendarAdapter(
            module.get_calendar("XSHG"),
            module.get_calendar("XHKG"),
            metadata=CalendarMetadata(
                "exchange_calendars",
                "exchange_calendars",
                _package_version("exchange-calendars"),
                ("XSHG", "XHKG"),
            ),
        )
    except Exception as exc:
        raise CalendarBlockedError(
            f"BLOCKED: exchange_calendars XSHG/XHKG unavailable: {exc}"
        ) from exc


def _load_pandas_market_calendars() -> ExchangeCalendarAdapter:
    try:
        module = import_module("pandas_market_calendars")
    except ImportError as exc:
        raise CalendarBlockedError(
            "BLOCKED: no supported exchange-calendar provider is available (exchange_calendars and "
            "pandas_market_calendars missing); no Mon-Fri fallback."
        ) from exc
    try:

        def get(names: tuple[str, ...]):
            available = set(module.get_calendar_names())
            selected = next((name for name in names if name in available), None)
            if selected is None:
                raise KeyError(names)
            return module.get_calendar(selected)

        return ExchangeCalendarAdapter(
            get(("XSHG", "SSE", "Shanghai Stock Exchange")),
            get(("XHKG", "HKEX", "Hong Kong Stock Exchange")),
            metadata=CalendarMetadata(
                "pandas_market_calendars",
                "pandas_market_calendars",
                _package_version("pandas-market-calendars"),
                ("XSHG", "XHKG"),
            ),
        )
    except Exception as exc:
        raise CalendarBlockedError(
            f"BLOCKED: pandas_market_calendars XSHG/XHKG unavailable: {exc}"
        ) from exc


def cn_hk_calendar(*, provider: ExchangeCalendarAdapter | None = None) -> ExchangeCalendarAdapter:
    """Return an injected adapter or the first supported real provider."""
    if provider is not None:
        return provider
    try:
        return _load_exchange_calendars()
    except CalendarBlockedError as first:
        try:
            return _load_pandas_market_calendars()
        except CalendarBlockedError as second:
            raise CalendarBlockedError(f"{second}; exchange_calendars detail: {first}") from second


def weekly_decision_dates(
    start: date, end: date, *, provider: ExchangeCalendarAdapter | None = None
) -> list[date]:
    """Weekly last common CN/HK session dates, inclusive of *start* and *end*."""
    return cn_hk_calendar(provider=provider).weekly_decision_dates(start, end)
