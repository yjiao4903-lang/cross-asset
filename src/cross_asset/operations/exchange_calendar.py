"""Optional exchange-calendar integration for session-aware decisions and freshness.

The project reuses installed ``exchange_calendars`` / ``pandas_market_calendars``
through this thin adapter. Missing or unsupported provider calendars are hard
BLOCKED states; there is no weekday approximation.
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

    def __init__(
        self,
        cn: Any | None = None,
        hk: Any | None = None,
        *,
        metadata: CalendarMetadata,
        calendars: dict[str, Any] | None = None,
    ):
        if calendars is None:
            if cn is None or hk is None:
                raise ValueError("XSHG/XHKG calendars required")
            calendars = {"XSHG": cn, "XHKG": hk}
        self._calendars = dict(calendars)
        self.metadata = metadata

    def sessions(self, market: str, start: date, end: date) -> set[date]:
        try:
            calendar = self._calendars[market]
        except KeyError as exc:
            raise CalendarBlockedError(f"BLOCKED: unsupported calendar {market}") from exc
        first = _as_date(calendar.first_session) if hasattr(calendar, "first_session") else start
        last = _as_date(calendar.last_session) if hasattr(calendar, "last_session") else end
        bounded_start = max(start, first)
        bounded_end = min(end, last)
        if bounded_end < bounded_start:
            return set()
        if hasattr(calendar, "sessions_in_range"):
            values = calendar.sessions_in_range(bounded_start, bounded_end)
        elif hasattr(calendar, "schedule"):
            values = calendar.schedule(start_date=bounded_start, end_date=bounded_end).index
        elif hasattr(calendar, "sessions"):
            values = calendar.sessions(bounded_start, bounded_end)
        else:
            raise TypeError(f"calendar {market} has no sessions API")
        return {_as_date(v) for v in values}

    def common_sessions(self, start: date, end: date) -> set[date]:
        return self.sessions("XSHG", start, end) & self.sessions("XHKG", start, end)

    def coverage(self) -> dict[str, dict[str, date | None]]:
        """Return provider-supported session bounds for audit output."""
        return {
            market: {
                "first_session": _as_date(calendar.first_session)
                if hasattr(calendar, "first_session")
                else None,
                "last_session": _as_date(calendar.last_session)
                if hasattr(calendar, "last_session")
                else None,
            }
            for market, calendar in self._calendars.items()
        }

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


_PMC_ALIASES = {
    "XSHG": ("XSHG", "SSE", "Shanghai Stock Exchange"),
    "XHKG": ("XHKG", "HKEX", "Hong Kong Stock Exchange"),
    "XNYS": ("XNYS", "NYSE", "New York Stock Exchange"),
}


def _load_exchange_calendars(
    markets: tuple[str, ...] = ("XSHG", "XHKG"),
) -> ExchangeCalendarAdapter:
    try:
        module = import_module("exchange_calendars")
    except ImportError as exc:
        raise CalendarBlockedError(
            "BLOCKED: exchange_calendars is unavailable; install it in the deployment environment "
            "or inject calendars explicitly (no Mon-Fri fallback)."
        ) from exc
    try:
        calendars = {market: module.get_calendar(market) for market in markets}
        return ExchangeCalendarAdapter(
            metadata=CalendarMetadata(
                "exchange_calendars",
                "exchange_calendars",
                _package_version("exchange-calendars"),
                markets,
            ),
            calendars=calendars,
        )
    except Exception as exc:
        names = "/".join(markets)
        raise CalendarBlockedError(
            f"BLOCKED: exchange_calendars {names} unavailable: {exc}"
        ) from exc


def _load_pandas_market_calendars(
    markets: tuple[str, ...] = ("XSHG", "XHKG"),
) -> ExchangeCalendarAdapter:
    try:
        module = import_module("pandas_market_calendars")
    except ImportError as exc:
        raise CalendarBlockedError(
            "BLOCKED: no supported exchange-calendar provider is available (exchange_calendars and "
            "pandas_market_calendars missing); no Mon-Fri fallback."
        ) from exc
    try:
        available = set(module.get_calendar_names())
        calendars = {}
        for market in markets:
            aliases = _PMC_ALIASES.get(market)
            if aliases is None:
                raise KeyError(market)
            selected = next((name for name in aliases if name in available), None)
            if selected is None:
                raise KeyError(aliases)
            calendars[market] = module.get_calendar(selected)
        return ExchangeCalendarAdapter(
            metadata=CalendarMetadata(
                "pandas_market_calendars",
                "pandas_market_calendars",
                _package_version("pandas-market-calendars"),
                markets,
            ),
            calendars=calendars,
        )
    except Exception as exc:
        names = "/".join(markets)
        raise CalendarBlockedError(
            f"BLOCKED: pandas_market_calendars {names} unavailable: {exc}"
        ) from exc


def exchange_calendar(
    markets: str | Iterable[str], *, provider: ExchangeCalendarAdapter | None = None
) -> ExchangeCalendarAdapter:
    """Return the existing upstream adapter for explicit canonical market ids."""
    requested = (markets,) if isinstance(markets, str) else tuple(markets)
    if not requested:
        raise CalendarBlockedError("BLOCKED: no calendar requested")
    if any(market not in _PMC_ALIASES for market in requested):
        raise CalendarBlockedError(
            "BLOCKED: unsupported calendar(s): " + ",".join(sorted(set(requested)))
        )
    if provider is not None:
        coverage = provider.coverage()
        missing = [market for market in requested if market not in coverage]
        if missing:
            raise CalendarBlockedError(
                "BLOCKED: injected provider missing calendar(s): " + ",".join(missing)
            )
        return provider
    try:
        return _load_exchange_calendars(requested)
    except CalendarBlockedError as first:
        try:
            return _load_pandas_market_calendars(requested)
        except CalendarBlockedError as second:
            raise CalendarBlockedError(f"{second}; exchange_calendars detail: {first}") from second


def cn_hk_calendar(*, provider: ExchangeCalendarAdapter | None = None) -> ExchangeCalendarAdapter:
    """Return the existing CN/HK adapter contract."""
    if provider is not None:
        # Preserve the pre-existing injectable Sprint2 contract: injected test or
        # local calendar objects need only expose the methods their caller uses.
        return provider
    return exchange_calendar(("XSHG", "XHKG"))


def weekly_decision_dates(
    start: date, end: date, *, provider: ExchangeCalendarAdapter | None = None
) -> list[date]:
    """Weekly last common CN/HK session dates, inclusive of *start* and *end*."""
    return cn_hk_calendar(provider=provider).weekly_decision_dates(start, end)
