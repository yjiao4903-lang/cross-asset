"""Weekly personal-review fact table.

Assembles point-in-time market levels and lookback changes for a Friday
week-end, compared on the Beijing clock. Missing values stay missing.
This module does not allocate, impute, or produce trade instructions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

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
DEFAULT_HOLD = {
    "decision": "不行动",
    "stance": "HOLD",
    "rule": "PERSONAL_WEEKLY default HOLD/no-action; human-controlled, not a trade signal.",
}


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
        raise FileNotFoundError(f"weekly review config not found: {config_path}")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(config.get("required_series"), list) or not config["required_series"]:
        raise ValueError("weekly review config must declare non-empty required_series")
    return config


def _review_time(config: dict[str, Any] | None) -> time:
    raw = (config or {}).get("review_local_time", "12:00")
    hour, minute = [int(part) for part in str(raw).split(":")[:2]]
    return time(hour, minute)


@dataclass(frozen=True)
class Observation:
    series_id: str
    observation_date: date
    value: float | None
    available_at: datetime
    source: str = "unspecified"


def parse_observations(rows: list[dict[str, Any]]) -> list[Observation]:
    out: list[Observation] = []
    for row in rows:
        out.append(
            Observation(
                series_id=str(row["series_id"]),
                observation_date=_as_date(row["observation_date"]),
                value=None if row.get("value") is None else float(row["value"]),
                available_at=to_beijing(row["available_at"]),
                source=str(row.get("source", "unspecified")),
            )
        )
        if out[-1].value is not None and not math.isfinite(out[-1].value):
            raise ValueError(f"non-finite observation value for {out[-1].series_id}")
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
    if current is None or prior is None or current.value is None or prior.value is None:
        return None
    if kind == "yield":
        return round((current.value - prior.value) * 100.0, 4)
    if prior.value == 0:
        return None
    return round(current.value / prior.value - 1.0, 6)


def build_fact_table(
    rows: list[Observation],
    *,
    as_of: date,
    cutoff: datetime,
    config: dict[str, Any] | None = None,
    week_end_date: date | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    end = week_end_date or week_end(as_of, cfg.get("week_end_weekday", "Friday"))
    lookbacks = cfg.get("lookbacks") or {
        "week": {"days": 7, "label": "1w"},
        "month": {"days": 21, "label": "21d_calendar"},
    }
    beijing_cutoff = to_beijing(cutoff)
    facts = []
    missing_levels = []
    missing_lookbacks = []
    unverified_sources = []
    for spec in cfg.get("required_series", []):
        series_id = spec["series_id"]
        kind = spec.get("kind", "price")
        current = latest_on_or_before(rows, series_id, end, beijing_cutoff)
        max_age = spec.get("max_age_days")
        stale = (
            current is not None
            and max_age is not None
            and (end - current.observation_date).days > int(max_age)
        )
        if stale:
            current = None
        expected_provider = spec.get("provider")
        source_status = "UNVERIFIED"
        if current is not None and current.value is not None:
            source_status = (
                "ADMITTED"
                if expected_provider is not None
                and current.source.lower() == str(expected_provider).lower()
                else "UNVERIFIED"
            )
            if source_status == "UNVERIFIED" and cfg.get("require_source_admission", False):
                unverified_sources.append(series_id)
        fact = {
            "label": spec.get("asset_id", series_id),
            "series_id": series_id,
            "kind": kind,
            "unit": spec.get("unit", "raw"),
            "period": end.isoformat(),
            "value": None if current is None else current.value,
            "observation_date": None if current is None else current.observation_date.isoformat(),
            "available_at": None if current is None else to_beijing(current.available_at).isoformat(),
            "source": "missing" if current is None or current.value is None else current.source,
            "usage": spec.get("usage", "PERSONAL_WEEKLY"),
            "source_status": source_status,
            "changes": {},
        }
        if current is None or current.value is None:
            missing_levels.append(series_id)
        for name, window in lookbacks.items():
            days = int(window["days"])
            prior = latest_on_or_before(rows, series_id, end - timedelta(days=days), beijing_cutoff)
            change = _change(current, prior, kind)
            label = window.get("label", name)
            fact["changes"][label] = {
                "value": change,
                "unit": "bp" if kind == "yield" else "fraction",
                "prior_observation_date": None if prior is None else prior.observation_date.isoformat(),
            }
            if name == "month" and label != "1m":
                fact["changes"]["1m"] = fact["changes"][label]
            if current is not None and change is None:
                missing_lookbacks.append(f"{series_id}:{label}")
        facts.append(fact)

    if missing_levels or unverified_sources:
        status = "DATA_BLOCKED"
    elif missing_lookbacks:
        status = "PARTIAL"
    else:
        status = "READY"
    return {
        "status": status,
        "timezone": "Asia/Shanghai",
        "usage": "PERSONAL_WEEKLY",
        "admission": "DEVELOPMENT_PRIOR",
        "as_of": as_of.isoformat(),
        "week_end": end.isoformat(),
        "data_cutoff": beijing_cutoff.isoformat(),
        "review_cutoff": beijing_cutoff.isoformat(),
        "effective_cutoff": beijing_cutoff.isoformat(),
        "missing_levels": missing_levels,
        "missing_lookbacks": missing_lookbacks,
        "unverified_sources": unverified_sources,
        "facts": facts,
    }
