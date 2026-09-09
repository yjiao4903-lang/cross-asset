"""Weekly personal-review fact table.

Assembles point-in-time market levels and lookback changes for a Friday
week-end, compared on the Beijing clock. Missing values stay missing.
This module does not allocate, impute, or produce trade instructions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from cross_asset.reports.research_brief import generate_research_brief

BEIJING = ZoneInfo("Asia/Shanghai")
WEEKDAYS = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}
DEFAULT_CONFIG = Path("config/weekly_review.yml")
DEFAULT_REVIEW_TIME = time(12, 0)


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return to_beijing(value).date()
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    return date.fromisoformat(text)


def to_beijing(value: Any) -> datetime:
    """Interpret naive timestamps as Beijing time; convert aware ones."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=BEIJING)
        return value.astimezone(BEIJING)
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, time(23, 59, 59), tzinfo=BEIJING)
    text = str(value).strip()
    if text.endswith("Z"):
        parsed = datetime.fromisoformat(text[:-1]).replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(BEIJING)
    if "T" in text:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=BEIJING)
        return parsed.astimezone(BEIJING)
    return datetime.combine(date.fromisoformat(text[:10]), time(23, 59, 59), tzinfo=BEIJING)


def week_end(as_of: date, week_end_weekday: str | int = "Friday") -> date:
    target = WEEKDAYS[week_end_weekday] if isinstance(week_end_weekday, str) else int(week_end_weekday)
    delta = (as_of.weekday() - target) % 7
    return as_of - timedelta(days=delta)


def default_review_cutoff(week_end_date: date, review_local_time: time | None = None) -> datetime:
    """Saturday 12:00 Beijing after the Friday week-end."""
    review_date = week_end_date + timedelta(days=1)
    stamp = review_local_time or DEFAULT_REVIEW_TIME
    return datetime.combine(review_date, stamp, tzinfo=BEIJING)


def load_weekly_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG
    if not config_path.exists():
        return {
            "week_end_weekday": "Friday",
            "review_weekday": "Saturday",
            "review_local_time": "12:00",
            "clock": {"timezone": "Asia/Shanghai"},
            "lookbacks": {
                "week": {"days": 7, "label": "1w"},
                "month": {"days": 21, "label": "1m"},
            },
            "required_series": [],
        }
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def _review_time(config: dict[str, Any] | None) -> time:
    raw = (config or {}).get("review_local_time", "12:00")
    hour, minute = [int(part) for part in str(raw).split(":")[:2]]
    return time(hour, minute)


@dataclass(frozen=True)
class Observation:
    series_id: str
    observation_date: date
    value: float
    available_at: datetime
    source: str = "unspecified"


def parse_observations(rows: list[dict[str, Any]]) -> list[Observation]:
    out: list[Observation] = []
    for row in rows:
        if row.get("value") is None:
            continue
        out.append(
            Observation(
                series_id=str(row["series_id"]),
                observation_date=_as_date(row["observation_date"]),
                value=float(row["value"]),
                available_at=to_beijing(row["available_at"]),
                source=str(row.get("source", "unspecified")),
            )
        )
    return out


def _visible(rows: list[Observation], cutoff: datetime) -> list[Observation]:
    edge = to_beijing(cutoff)
    return [row for row in rows if to_beijing(row.available_at) <= edge]


def latest_on_or_before(
    rows: list[Observation], series_id: str, as_of: date, cutoff: datetime
) -> Observation | None:
    eligible = [
        row
        for row in _visible(rows, cutoff)
        if row.series_id == series_id and row.observation_date <= as_of
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda row: (row.observation_date, to_beijing(row.available_at)))


def _change(current: Observation | None, prior: Observation | None, kind: str) -> float | None:
    if current is None or prior is None:
        return None
    if kind == "yield":
        return round((current.value - prior.value) * 100.0, 4)
    if prior.value == 0:
        return None
    return round(current.value / prior.value - 1.0, 6)
