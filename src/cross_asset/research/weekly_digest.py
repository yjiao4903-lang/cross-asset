"""Deterministic weekly digest written from this week's numbers.

Professional notes start with what happened, the binding constraint,
and the next-Saturday window. Labels stay downstream. This module
does not change stance or authorize trades.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from cross_asset.research.weekly_story import build_weekly_story

DEFAULT_CALENDAR = Path("config/weekly_calendar.yml")


def _chg(table: dict[str, Any], series_id: str, window: str = "1w") -> float | None:
    for item in table.get("facts") or []:
        if item.get("series_id") == series_id:
            raw = ((item.get("changes") or {}).get(window) or {}).get("value")
            return None if raw is None else float(raw)
    return None


def _val(table: dict[str, Any], series_id: str) -> float | None:
    for item in table.get("facts") or []:
        if item.get("series_id") == series_id:
            value = item.get("value")
            return None if value is None else float(value)
    return None


def _pct(value: float | None) -> str:
    if value is None:
        return "缺失"
    return f"{value * 100:+.2f}%"


def _bp(value: float | None) -> str:
    if value is None:
        return "缺失"
    return f"{value:+.1f}bp"


def _box(boxes: list[dict[str, Any]], label: str) -> str:
    for item in boxes:
        if item.get("label") == label:
            return str(item.get("value") or "不明")
    return "不明"


def _card(scorecard: list[dict[str, Any]], label: str) -> dict[str, Any]:
    for item in scorecard:
        if item.get("label") == label:
            return item
    return {}


def load_calendar(path: str | Path | None = None) -> list[dict[str, Any]]:
    raw_path = Path(path) if path else DEFAULT_CALENDAR
    if not raw_path.exists():
        return []
    payload = yaml.safe_load(raw_path.read_text(encoding="utf-8")) or {}
    events = payload.get("events") or []
    return [item for item in events if isinstance(item, dict)]


def upcoming_events(
    events: list[dict[str, Any]], week_end: date, horizon_days: int = 14
) -> list[dict[str, Any]]:
    edge = week_end + timedelta(days=horizon_days)
    out = []
    for item in events:
        try:
            day = date.fromisoformat(str(item.get("date", ""))[:10])
        except ValueError:
            continue
        if week_end < day <= edge:
            row = dict(item)
            row["date"] = day.isoformat()
            out.append(row)
    return out


def _what_happened(table: dict[str, Any]) -> str:
    cn = _chg(table, "CN_EQ_LARGE")
    hk = _chg(table, "HK_EQ")
    us = _chg(table, "US_EQ")
    bond = _chg(table, "CN_BOND_10Y")
    gold = _chg(table, "GOLD")
    copper = _chg(table, "COPPER")
    return (
        f"A股一周{_pct(cn)}，港股{_pct(hk)}，美股{_pct(us)}；"
        f"中国10Y {_bp(bond)}，黄金{_pct(gold)}，铜{_pct(copper)}。"
    )


def _binding_constraint(
    table: dict[str, Any],
    boxes: list[dict[str, Any]],
    scorecard: list[dict[str, Any]],
    depth: dict[str, Any],
) -> str:
    growth = _box(boxes, "增长")
    liquidity = _box(boxes, "流动性")
    bond = _card(scorecard, "CN_BOND")
    level = _val(table, "CN_BOND_10Y")
    links = {item.get("label"): item for item in depth.get("transmission") or []}
    priced = depth.get("priced") or depth.get("priced_residual") or []
    residuals = [
        str(item.get("claim"))
        for item in priced
        if item.get("state") == "残差"
    ]
    growth_link = (links.get("增长复合体") or {}).get("status")
    gold_link = (links.get("黄金-利率对冲") or {}).get("status")
    duration = (links.get("国内利率传导") or {}).get("status")
    parts = []
    if growth == "走弱" and growth_link == "断裂":
        parts.append(
            "增长标签偏弱，但铜与A股没有同向，弱增长还是残差而不是已定价。"
        )
    if liquidity == "松" and duration == "接通":
        if bond.get("odds") == "差" and level is not None:
            parts.append(
                f"资金松已传到国债，但10Y已在{level:.2f}，胜率好、赔率差，"
                "不能把宽松直接写成加久期。"
            )
        else:
            parts.append("国内宽松传导接通，这是本周唯一被价格确认的腿。")
    if gold_link == "断裂":
        parts.append(
            "黄金与美债利率同向，不能再用降息交易解释金价。"
        )
    if not parts:
        if residuals:
            parts.append("残差在" + "、".join(residuals) + "，不足以改立场。")
        else:
            parts.append("层间没有同时对齐，约束仍是不行动。")
    return "".join(parts)


def _disagreement(reviews: list[dict[str, Any]]) -> str:
    conflicts = []
    agrees = []
    for item in reviews:
        house = item.get("house") or "未署名"
        for check in item.get("checks") or []:
            label = check.get("label")
            status = check.get("status")
            if status == "对照冲突":
                conflicts.append(
                    f"{house}把{label}写成{check.get('stated')}，"
                    f"价格层是{check.get('computed')}"
                )
            elif status == "同意":
                agrees.append(str(label))
    if conflicts:
        return "与个人纪要的分歧：" + "；".join(conflicts) + "。冲突只记录，不交易。"
    if agrees:
        return "个人纪要与四格在" + "、".join(agrees) + "上同向。"
    return "本周没有可对照的卖方/个人纪要四格。"


def build_weekly_digest(
    *,
    table: dict[str, Any],
    boxes: list[dict[str, Any]],
    scorecard: list[dict[str, Any]],
    stance: dict[str, Any],
    reviews: list[dict[str, Any]] | None = None,
    depth: dict[str, Any] | None = None,
    calendar_path: str | Path | None = None,
    story: dict[str, Any] | None = None,
) -> dict[str, Any]:
    week_end = date.fromisoformat(str(table.get("week_end")))
    depth = depth or {}
    events = upcoming_events(load_calendar(calendar_path), week_end)
    happened = _what_happened(table)
    constraint = _binding_constraint(table, boxes, scorecard, depth)
    split = _disagreement(reviews or [])
    decision = stance.get("decision") or "不行动"
    if story is None:
        story = build_weekly_story(
            table=table,
            boxes=boxes,
            scorecard=scorecard,
            stance=stance,
            depth=depth,
        )
    headline = story.get("headline") or happened
    lines = [
        "",
        "## 本周读法",
        "",
        f"- 观察周 {week_end.isoformat()}。{headline}",
        f"- 六条腿备查：{happened}",
        f"- 主导矛盾：{constraint}",
        f"- {split}",
        f"- 结论仍是{decision}。下面的四格和评分是证据，不是另一套口号。",
        "",
        "## 下周六前要看的窗口",
        "",
    ]
    if not events:
        lines.append("- 日历未填本窗口事件。可在 config/weekly_calendar.yml 补。")
    for item in events:
        why = item.get("why") or "关系本周残差能否被证伪"
        lines.append(f"- {item['date']} {item.get('label')}：{why}")
    return {
        "status": "READY",
        "happened": happened,
        "constraint": constraint,
        "headline": headline,
        "events": events,
        "story": story,
        "markdown": "\n".join(lines) + "\n",
    }


__all__ = ["build_weekly_digest", "load_calendar", "upcoming_events"]
