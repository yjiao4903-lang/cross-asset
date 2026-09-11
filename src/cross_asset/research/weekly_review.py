"""Weekly personal-review fact table runner."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from cross_asset.reports.research_brief import generate_research_brief
from cross_asset.research.weekly_core import (
    BEIJING,
    DEFAULT_HOLD,
    Observation,
    _as_date,
    _review_time,
    build_fact_table,
    default_review_cutoff,
    latest_on_or_before,
    load_weekly_config,
    parse_observations,
    to_beijing,
    week_end,
)


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
    if table.get("unverified_sources"):
        parts.append("来源未核验: " + ", ".join(table["unverified_sources"]))
    parts.append("时钟为北京时间；周复盘不产生交易建议，也不改战略权重。")
    return "；".join(parts)


def _market_facts(table: dict[str, Any], changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                    f"usage={item.get('usage', 'PERSONAL_WEEKLY')}; 1w={change_1w.get('value')}"
                ),
            }
        )
    facts.extend(changes)
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
    week_end_date: str | date | None = None,
    review_cutoff: Any | None = None,
) -> dict[str, Any]:
    payload = json.loads(Path(observations_json).read_text(encoding="utf-8"))
    config = load_weekly_config(config_path)
    rows = parse_observations(list(payload.get("observations") or payload.get("rows") or []))
    review_date = _as_date(as_of)
    observation_week_end = _as_date(week_end_date) if week_end_date is not None else None
    source_cutoff = payload.get("data_cutoff")
    requested_cutoff = review_cutoff if review_cutoff is not None else source_cutoff
    review_end = observation_week_end or week_end(review_date, config.get("week_end_weekday", "Friday"))
    review_boundary = default_review_cutoff(review_end, _review_time(config))
    if review_cutoff is not None:
        requested = to_beijing(review_cutoff)
        if requested > review_boundary:
            raise ValueError(f"review_cutoff exceeds configured boundary {review_boundary.isoformat()}")
        if observation_week_end is None and requested.date() > review_date:
            raise ValueError(
                "a cutoff after as_of requires explicit --week-end to separate observation and review dates"
            )
        cutoff = requested
    else:
        cutoff = resolve_cutoff(
            as_of=review_date,
            payload_cutoff=source_cutoff,
            config=config,
        )
    table = build_fact_table(
        rows,
        as_of=review_date,
        cutoff=cutoff,
        config=config,
        week_end_date=observation_week_end,
    )
    table["requested_cutoff"] = None if requested_cutoff is None else to_beijing(requested_cutoff).isoformat()
    table["source_cutoff"] = None if source_cutoff is None else to_beijing(source_cutoff).isoformat()
    table["cutoff_boundary"] = review_boundary.isoformat()
    table["cutoff_adjusted"] = requested_cutoff is not None and to_beijing(requested_cutoff) != cutoff
    prior = None
    if prior_snapshot and Path(prior_snapshot).exists():
        prior = json.loads(Path(prior_snapshot).read_text(encoding="utf-8"))
    changes = compare_weeks(table, prior)
    stance = dict(DEFAULT_HOLD)
    brief = generate_research_brief(
        output=output,
        as_of=table["as_of"],
        data_cutoff=table["effective_cutoff"],
        sources=["weekly_review", "PERSONAL_WEEKLY", "DEVELOPMENT_PRIOR"],
        completeness=table["status"],
        limitations=_limitations(table),
        market_facts=_market_facts(table, changes),
        computed_signals=[],
        decision_record=f"{stance['decision']}。{stance['stance']}。{stance['rule']}",
        next_check=(week_end(review_date) + timedelta(days=7)).isoformat(),
        research_question="本周可见价格/收益率事实是否足够支持人工判断？",
        supporting_evidence="见事实表与 requested/source/effective cutoff；缺水平保持 DATA_BLOCKED。",
        counterevidence="缺回溯为 PARTIAL；未知不等于零。默认不行动。",
    )
    brief_path = Path(brief)
    appendix = "\n".join(
        [
            "",
            "## 相对上周",
            "",
            *(
                f"- {item.get('label')}: {item.get('value')} {item.get('unit')} ({item.get('period')})"
                for item in changes
            ),
            "",
            "## 默认立场",
            "",
            f"- {stance['decision']} / {stance['stance']}",
            f"- {stance['rule']}",
            f"- usage={table['usage']}; admission={table['admission']}",
            "",
        ]
    )
    brief_path.write_text(brief_path.read_text(encoding="utf-8") + appendix, encoding="utf-8")
    table["stance"] = stance
    snap_path = Path(snapshot_output or Path(output).with_suffix(".snapshot.json"))
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": table["status"],
        "timezone": "Asia/Shanghai",
        "usage": "PERSONAL_WEEKLY",
        "admission": "DEVELOPMENT_PRIOR",
        "week_end": table["week_end"],
        "data_cutoff": table["data_cutoff"],
        "review_cutoff": table["review_cutoff"],
        "requested_cutoff": table["requested_cutoff"],
        "source_cutoff": table["source_cutoff"],
        "effective_cutoff": table["effective_cutoff"],
        "cutoff_boundary": table["cutoff_boundary"],
        "cutoff_adjusted": table["cutoff_adjusted"],
        "brief_output": str(brief_path),
        "snapshot_output": str(snap_path),
        "missing_levels": table["missing_levels"],
        "missing_lookbacks": table["missing_lookbacks"],
        "unverified_sources": table["unverified_sources"],
        "facts": table["facts"],
        "prior_week_changes": changes,
        "stance": stance,
    }


__all__ = [
    "BEIJING",
    "DEFAULT_HOLD",
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
