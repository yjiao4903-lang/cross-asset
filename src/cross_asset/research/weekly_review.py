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


def build_fact_table(
    rows: list[Observation],
    *,
    as_of: date,
    cutoff: datetime,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    end = week_end(as_of, cfg.get("week_end_weekday", "Friday"))
    lookbacks = cfg.get("lookbacks") or {
        "week": {"days": 7, "label": "1w"},
        "month": {"days": 21, "label": "1m"},
    }
    beijing_cutoff = to_beijing(cutoff)
    facts = []
    missing_levels = []
    missing_lookbacks = []
    for spec in cfg.get("required_series", []):
        series_id = spec["series_id"]
        kind = spec.get("kind", "price")
        current = latest_on_or_before(rows, series_id, end, beijing_cutoff)
        fact = {
            "label": spec.get("asset_id", series_id),
            "series_id": series_id,
            "kind": kind,
            "unit": spec.get("unit", "raw"),
            "period": end.isoformat(),
            "value": None if current is None else current.value,
            "observation_date": None if current is None else current.observation_date.isoformat(),
            "available_at": None if current is None else to_beijing(current.available_at).isoformat(),
            "source": "missing" if current is None else current.source,
            "changes": {},
        }
        if current is None:
            missing_levels.append(series_id)
        for name, window in lookbacks.items():
            days = int(window["days"])
            prior = latest_on_or_before(
                rows, series_id, end - timedelta(days=days), beijing_cutoff
            )
            change = _change(current, prior, kind)
            fact["changes"][window.get("label", name)] = {
                "value": change,
                "unit": "bp" if kind == "yield" else "fraction",
                "prior_observation_date": None
                if prior is None
                else prior.observation_date.isoformat(),
            }
            if current is not None and change is None:
                missing_lookbacks.append(f"{series_id}:{window.get('label', name)}")
        facts.append(fact)

    if missing_levels:
        status = "DATA_BLOCKED"
    elif missing_lookbacks:
        status = "PARTIAL"
    else:
        status = "READY"
    return {
        "status": status,
        "timezone": "Asia/Shanghai",
        "as_of": as_of.isoformat(),
        "week_end": end.isoformat(),
        "data_cutoff": beijing_cutoff.isoformat(),
        "missing_levels": missing_levels,
        "missing_lookbacks": missing_lookbacks,
        "facts": facts,
    }


def compare_weeks(current: dict[str, Any], prior: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not prior:
        return [
            {
                "label": "prior_week",
                "value": "未提供上周快照",
                "unit": "status",
                "period": current.get("week_end"),
                "source": "weekly_review",
            }
        ]
    prior_map = {item["series_id"]: item for item in prior.get("facts", [])}
    out = []
    for item in current.get("facts", []):
        old = prior_map.get(item["series_id"])
        if not old or item["value"] is None or old.get("value") is None:
            out.append(
                {
                    "label": f"{item['label']} vs prior week",
                    "value": "不可比",
                    "unit": "status",
                    "period": f"{old.get('period') if old else 'missing'} -> {item.get('period')}",
                    "source": "weekly_review",
                }
            )
            continue
        if item.get("kind") == "yield":
            delta = round((float(item["value"]) - float(old["value"])) * 100.0, 4)
            unit = "bp"
        else:
            baseline = float(old["value"])
            delta = None if baseline == 0 else round(float(item["value"]) / baseline - 1.0, 6)
            unit = "fraction"
        out.append(
            {
                "label": f"{item['label']} vs prior week",
                "value": delta,
                "unit": unit,
                "period": f"{old.get('period')} -> {item.get('period')}",
                "source": "weekly_review",
            }
        )
    return out


def _limitations(table: dict[str, Any]) -> str:
    parts = []
    if table["missing_levels"]:
        parts.append("缺最新水平: " + ", ".join(table["missing_levels"]))
    if table["missing_lookbacks"]:
        parts.append("缺回溯窗口: " + ", ".join(table["missing_lookbacks"]))
    parts.append("时钟为北京时间；周复盘不产生交易建议，也不改战略权重。")
    return "；".join(parts)


def _market_facts(table: dict[str, Any]) -> list[dict[str, Any]]:
    facts = []
    for item in table["facts"]:
        change_1w = (item.get("changes") or {}).get("1w", {})
        facts.append(
            {
                "label": item["label"],
                "value": item["value"] if item["value"] is not None else "缺失",
                "unit": item["unit"],
                "period": item.get("observation_date") or item["period"],
                "source": (
                    f"{item['source']}; series_id={item['series_id']}; "
                    f"1w={change_1w.get('value')}"
                ),
            }
        )
    return facts


def resolve_cutoff(
    *,
    as_of: date,
    payload_cutoff: Any | None,
    config: dict[str, Any] | None = None,
) -> datetime:
    cfg = config or {}
    end = week_end(as_of, cfg.get("week_end_weekday", "Friday"))
    review_cutoff = default_review_cutoff(end, _review_time(cfg))
    if payload_cutoff is None:
        cap = datetime.combine(as_of, time(23, 59, 59), tzinfo=BEIJING)
        return min(review_cutoff, cap)
    parsed = to_beijing(payload_cutoff)
    cap = datetime.combine(as_of, time(23, 59, 59), tzinfo=BEIJING)
    return min(parsed, cap)


def run_weekly_review(
    *,
    as_of: str,
    observations_json: str | Path,
    output: str | Path = "artifacts/reports/weekly_review.md",
    prior_snapshot: str | Path | None = None,
    snapshot_output: str | Path | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    payload = json.loads(Path(observations_json).read_text(encoding="utf-8"))
    config = load_weekly_config(config_path)
    rows = parse_observations(list(payload.get("observations") or payload.get("rows") or []))
    review_date = _as_date(as_of)
    cutoff = resolve_cutoff(
        as_of=review_date,
        payload_cutoff=payload.get("data_cutoff"),
        config=config,
    )
    table = build_fact_table(rows, as_of=review_date, cutoff=cutoff, config=config)
    prior = None
    if prior_snapshot and Path(prior_snapshot).exists():
        prior = json.loads(Path(prior_snapshot).read_text(encoding="utf-8"))
    changes = compare_weeks(table, prior)
    brief = generate_research_brief(
        output=output,
        as_of=table["as_of"],
        data_cutoff=table["data_cutoff"],
        sources=["weekly_review"],
        completeness=table["status"],
        limitations=_limitations(table),
        market_facts=_market_facts(table),
        prior_week_changes=changes,
        decision_record="不行动：周复盘默认观察，人工填写后才形成候选调整。",
        next_check=(week_end(review_date) + timedelta(days=7)).isoformat(),
    )
    snap_path = Path(snapshot_output or Path(output).with_suffix(".snapshot.json"))
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": table["status"],
        "timezone": "Asia/Shanghai",
        "week_end": table["week_end"],
        "data_cutoff": table["data_cutoff"],
        "brief_output": str(brief),
        "snapshot_output": str(snap_path),
        "missing_levels": table["missing_levels"],
        "missing_lookbacks": table["missing_lookbacks"],
        "facts": table["facts"],
        "prior_week_changes": changes,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Weekly personal review fact table")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--observations-json", required=True)
    parser.add_argument("--output", default="artifacts/reports/weekly_review.md")
    parser.add_argument("--prior-snapshot")
    parser.add_argument("--snapshot-output")
    parser.add_argument("--config")
    args = parser.parse_args()
    result = run_weekly_review(
        as_of=args.as_of,
        observations_json=args.observations_json,
        output=args.output,
        prior_snapshot=args.prior_snapshot,
        snapshot_output=args.snapshot_output,
        config_path=args.config,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()


__all__ = [
    "BEIJING",
    "Observation",
    "build_fact_table",
    "compare_weeks",
    "default_review_cutoff",
    "latest_on_or_before",
    "parse_observations",
    "resolve_cutoff",
    "run_weekly_review",
    "to_beijing",
    "week_end",
]
