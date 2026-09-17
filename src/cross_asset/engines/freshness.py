"""Calendar-aware freshness interface for formal and monitoring consumers (fail-closed).

Series may explicitly bind either to the legacy evidence-backed project calendar
configuration or to the existing upstream exchange-calendar adapter. Missing or
unsupported mappings remain BLOCKED. No weekend heuristic, elapsed-hour fallback,
or implicit lag budget is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

from cross_asset.operations.calendar import MarketCalendar
from cross_asset.operations.exchange_calendar import CalendarBlockedError, exchange_calendar

_MAX_CALENDAR_WALK_DAYS = 370
_EXCHANGE_ADAPTER_SOURCE = "exchange_adapter"


@dataclass(frozen=True)
class FreshnessResult:
    series_id: str
    status: str  # OK | STALE | BLOCKED
    reason: str
    calendar: str | None = None
    expected_session: date | None = None
    latest_observation_date: date | None = None
    lag_sessions: int | None = None

    @property
    def healthy(self) -> bool:
        return self.status == "OK"

    def blocker(self) -> str | None:
        return None if self.healthy else f"{self.status}:{self.reason}"


def load_series_calendar_mapping(
    config_path: str | Path = "config/series_calendars.yml",
) -> dict[str, dict]:
    """Load the explicit series -> calendar mapping; missing file stays empty."""

    try:
        payload = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return {}
    entries = payload.get("series_calendars", {}) if isinstance(payload, dict) else {}
    if not isinstance(entries, dict):
        return {}
    return {
        str(series_id): entry if isinstance(entry, dict) else {"calendar": entry}
        for series_id, entry in entries.items()
    }


def _exchange_freshness(
    series_id: str,
    *,
    latest_observation_date: date,
    market_data_cutoff: date,
    calendar_name: str,
    max_lag: int,
) -> FreshnessResult:
    def blocked(reason: str) -> FreshnessResult:
        return FreshnessResult(series_id, "BLOCKED", reason)

    if latest_observation_date > market_data_cutoff:
        return blocked("observation_after_market_cutoff")
    try:
        adapter = exchange_calendar(calendar_name)
        coverage = adapter.coverage().get(calendar_name, {})
        first = coverage.get("first_session")
        last = coverage.get("last_session")
        if first is not None and latest_observation_date < first:
            return blocked("calendar_coverage_missing")
        if last is not None and market_data_cutoff > last:
            return blocked("calendar_coverage_missing")
        sessions = adapter.sessions(
            calendar_name,
            latest_observation_date,
            market_data_cutoff,
        )
    except (CalendarBlockedError, KeyError, TypeError, ValueError):
        return blocked("calendar_unavailable")

    eligible_sessions = sorted(
        day for day in sessions if latest_observation_date < day <= market_data_cutoff
    )
    lag = len(eligible_sessions)
    cutoff_sessions = [day for day in sessions if day <= market_data_cutoff]
    expected = max(cutoff_sessions) if cutoff_sessions else None
    if lag > max_lag:
        return FreshnessResult(
            series_id,
            "STALE",
            "calendar_lag_exceeds_max_lag_sessions",
            calendar=calendar_name,
            expected_session=expected,
            latest_observation_date=latest_observation_date,
            lag_sessions=lag,
        )
    return FreshnessResult(
        series_id,
        "OK",
        "fresh_within_calendar_lag",
        calendar=calendar_name,
        expected_session=expected,
        latest_observation_date=latest_observation_date,
        lag_sessions=lag,
    )


def evaluate_series_freshness(
    series_id: str,
    *,
    latest_observation_date: date | None,
    market_data_cutoff: date,
    calendar_config: str | Path = "config/calendars.yml",
    series_calendar_config: str | Path = "config/series_calendars.yml",
    mapping: dict[str, dict] | None = None,
) -> FreshnessResult:
    """Evaluate calendar-driven freshness for one series at the market cutoff.

    The lag budget is the number of open sessions after the latest approved or
    monitoring observation date up to and including the market-data cutoff. Any
    missing evidence (mapping, supported calendar, explicit lag budget, or
    coverage) fails closed rather than defaulting to fresh.
    """

    def blocked(reason: str) -> FreshnessResult:
        return FreshnessResult(series_id, "BLOCKED", reason)

    if latest_observation_date is None:
        return blocked("no_formal_observation")

    mapping = mapping if mapping is not None else load_series_calendar_mapping(series_calendar_config)
    entry = mapping.get(series_id)
    if not entry:
        return blocked("calendar_mapping_missing")

    calendar_name = entry.get("calendar")
    if not calendar_name or not isinstance(calendar_name, str):
        return blocked("calendar_not_named")

    max_lag = entry.get("max_lag_sessions")
    if max_lag is None:
        return blocked("max_lag_sessions_not_configured")
    try:
        max_lag = int(max_lag)
    except (TypeError, ValueError):
        return blocked("max_lag_sessions_invalid")
    if max_lag < 0:
        return blocked("max_lag_sessions_invalid")

    calendar_source = str(entry.get("calendar_source") or "config").strip().lower()
    if calendar_source == _EXCHANGE_ADAPTER_SOURCE:
        return _exchange_freshness(
            series_id,
            latest_observation_date=latest_observation_date,
            market_data_cutoff=market_data_cutoff,
            calendar_name=calendar_name,
            max_lag=max_lag,
        )
    if calendar_source != "config":
        return blocked("calendar_source_unsupported")

    try:
        calendar = MarketCalendar(str(calendar_name), calendar_config)
    except (OSError, KeyError, yaml.YAMLError):
        return blocked("calendar_unavailable")
    if not calendar.verified:
        return blocked("calendar_unverified")

    lag = 0
    day = market_data_cutoff
    for _ in range(_MAX_CALENDAR_WALK_DAYS):
        session_status = calendar.session_status(day)
        if session_status == "UNKNOWN":
            return blocked("calendar_coverage_missing")
        if day == latest_observation_date:
            return FreshnessResult(
                series_id,
                "OK",
                "fresh_within_calendar_lag",
                calendar=str(calendar_name),
                expected_session=market_data_cutoff,
                latest_observation_date=latest_observation_date,
                lag_sessions=lag,
            )
        if session_status == "OPEN":
            lag += 1
            if lag > max_lag:
                return FreshnessResult(
                    series_id,
                    "STALE",
                    "calendar_lag_exceeds_max_lag_sessions",
                    calendar=str(calendar_name),
                    expected_session=market_data_cutoff,
                    latest_observation_date=latest_observation_date,
                    lag_sessions=lag,
                )
        day -= timedelta(days=1)
    return FreshnessResult(
        series_id,
        "STALE",
        "calendar_walk_exhausted",
        calendar=str(calendar_name),
        expected_session=market_data_cutoff,
        latest_observation_date=latest_observation_date,
        lag_sessions=None,
    )


def evaluate_freshness(
    series_ids,
    *,
    latest_observation_dates: dict[str, date | None],
    market_data_cutoff: date,
    calendar_config: str | Path = "config/calendars.yml",
    series_calendar_config: str | Path = "config/series_calendars.yml",
) -> dict[str, FreshnessResult]:
    """Evaluate freshness for several series and return per-series results."""

    mapping = load_series_calendar_mapping(series_calendar_config)
    return {
        series_id: evaluate_series_freshness(
            series_id,
            latest_observation_date=latest_observation_dates.get(series_id),
            market_data_cutoff=market_data_cutoff,
            calendar_config=calendar_config,
            series_calendar_config=series_calendar_config,
            mapping=mapping,
        )
        for series_id in series_ids
    }


__all__ = [
    "FreshnessResult",
    "evaluate_freshness",
    "evaluate_series_freshness",
    "load_series_calendar_mapping",
]
