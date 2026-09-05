"""Calendar-aware freshness interface for formal consumers (fail-closed).

Issue #18 owns the consumer-side freshness semantics; the real per-series
calendar evidence (holidays, early closes, CN_INTERBANK make-up weekends and
the six Wind source confirmations) is owned by Issue #21. Until a series is
explicitly mapped to a VERIFIED calendar with an explicit session-lag budget,
this interface refuses to certify freshness and formal consumers must remain
DATA_BLOCKED/FROZEN. No weekend heuristic or implicit default lag is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

from cross_asset.operations.calendar import MarketCalendar

_MAX_CALENDAR_WALK_DAYS = 370


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

    The lag budget is the number of open sessions after the latest approved
    observation date up to and including the market-data cutoff. Any missing
    piece of evidence (mapping, verified calendar, covered year, explicit lag
    budget) fails closed as BLOCKED rather than defaulting to fresh.
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
