"""Auditable, configuration-backed market calendar contract."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml


def validate_calendar_entry(entry: dict) -> list[str]:
    required = ("calendar_id", "source", "source_version", "timezone", "regular_close", "verified", "evidence", "reviewer", "approved_at")
    errors = [f"missing_{key}" for key in required if key not in entry]
    if entry.get("verified") is not True or entry.get("capability_status") != "VERIFIED":
        errors.append("calendar_unverified")
    return sorted(errors)


class MarketCalendar:
    def __init__(self, name: str, config_path: str | Path = "config/calendars.yml"):
        raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        item = (raw.get("calendars") or {}).get(name)
        if not isinstance(item, dict):
            raise KeyError(f"calendar not configured: {name}")
        self.name, self.timezone = name, item.get("timezone", "UTC")
        self.capability_status = item.get("capability_status", "UNVERIFIED")
        self.source, self.version = item.get("source", "UNVERIFIED"), item.get("version", "TBD")
        self.calendar_id = item.get("calendar_id", name)
        self.verified = item.get("verified", self.capability_status == "VERIFIED") is True and self.capability_status == "VERIFIED"
        self.evidence = item.get("evidence") or []
        self.reviewer, self.approved_at = item.get("reviewer"), item.get("approved_at")
        self.open_time = time.fromisoformat(item.get("open_time", "00:00"))
        self.close_time = time.fromisoformat(item.get("close_time", "23:59"))
        self.covered_years = set(item.get("covered_years") or [])
        self.holidays = {date.fromisoformat(str(x)) for x in item.get("holidays", [])}
        self.early_closes = dict(item.get("early_closes") or {})

    def session_status(self, day: date) -> str:
        if not self.verified or day.year not in self.covered_years:
            return "UNKNOWN"
        return "CLOSED" if day.weekday() >= 5 or day in self.holidays else "OPEN"

    def is_session(self, day: date) -> bool:
        return self.session_status(day) == "OPEN"

    def previous_session(self, day: date) -> date | None:
        for offset in range(1, 370):
            candidate = day - timedelta(days=offset)
            if self.is_session(candidate):
                return candidate
        return None

    def next_session(self, day: date) -> date | None:
        for offset in range(1, 370):
            candidate = day + timedelta(days=offset)
            if self.is_session(candidate):
                return candidate
        return None

    def last_available_session(self, decision_time: datetime | date) -> date | None:
        if isinstance(decision_time, datetime):
            if decision_time.tzinfo is None:
                return None
            local = decision_time.astimezone(ZoneInfo(self.timezone))
            day = local.date()
            close = time.fromisoformat(self.early_closes.get(str(day), self.early_closes.get(day.isoformat(), self.close_time.isoformat())))
            if local.time() < close:
                return self.previous_session(day)
        else:
            day = decision_time
        if self.session_status(day) == "UNKNOWN":
            return None
        return day if self.is_session(day) else self.previous_session(day)


def last_common_session(decision_time: datetime | date, calendars: list[MarketCalendar]) -> date | None:
    if not calendars:
        return None
    if isinstance(decision_time, datetime) and decision_time.tzinfo is None:
        return None
    day = decision_time.date() if isinstance(decision_time, datetime) else decision_time
    for _ in range(370):
        statuses = [cal.session_status(day) for cal in calendars]
        if "UNKNOWN" in statuses:
            return None
        if all(status == "OPEN" for status in statuses):
            return day
        day -= timedelta(days=1)
    return None


def calendar_status(name: str, day: date, config_path: str | Path = "config/calendars.yml") -> str:
    return MarketCalendar(name, config_path).session_status(day)


# Optional real-exchange adapter. Kept as lazy imports so existing configuration
# calendars and reports remain usable without third-party calendar packages.
def real_cnhk_weekly_decision_dates(start: date, end: date, *, provider=None) -> list[date]:
    from .exchange_calendar import weekly_decision_dates
    return weekly_decision_dates(start, end, provider=provider)
