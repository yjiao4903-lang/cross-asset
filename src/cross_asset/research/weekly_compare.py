"""Week-over-week narrative for the personal replay.

Compares this Saturday's four-box and scorecard with the prior Friday
snapshot. The compare never changes stance or authorizes a trade.
"""

from __future__ import annotations

from typing import Any


def _box_map(payload: dict[str, Any] | None) -> dict[str, str]:
    layers = (payload or {}).get("layers") or {}
    return {
        str(item.get("label")): str(item.get("value"))
        for item in layers.get("macro_boxes") or []
        if item.get("label")
    }


def _card_map(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    layers = (payload or {}).get("layers") or {}
    return {
        str(item.get("label")): item
        for item in layers.get("scorecard") or []
        if item.get("label") and item.get("label") != "macro_context"
    }


def build_weekly_compare(
    current: dict[str, Any],
    prior: dict[str, Any] | None,
    layers: dict[str, Any],
) -> dict[str, Any]:
    if not prior:
        return {
            "status": "SKIPPED",
            "rows": [],
            "markdown": "\n## 两周对照\n\n- 未提供上周快照，本周只记录单周事实。\n",
        }
    prior_boxes = _box_map(prior)
    current_boxes = {
        str(item.get("label")): str(item.get("value"))
        for item in layers.get("macro_boxes") or []
        if item.get("label")
    }
    rows: list[dict[str, Any]] = []
    for label in ("增长", "通胀", "流动性", "海外约束"):
        old = prior_boxes.get(label)
        now = current_boxes.get(label)
        if old is None:
            state = "上周缺失"
        elif now is None:
            state = "本周缺失"
        elif old == now:
            state = "不变"
        else:
            state = f"{old} → {now}"
        rows.append(
            {"kind": "box", "label": label, "prior": old, "current": now, "state": state}
        )
    prior_card = _card_map(prior)
    for item in layers.get("scorecard") or []:
        label = item.get("label")
        if not label or label == "macro_context":
            continue
        old = prior_card.get(str(label))
        now_win = item.get("win")
        now_odds = item.get("odds")
        if not old:
            state = "上周无评分"
        elif old.get("win") == now_win and old.get("odds") == now_odds:
            state = "不变"
        else:
            state = (
                f"{old.get('win')}/{old.get('odds')} → {now_win}/{now_odds}"
            )
        rows.append(
            {
                "kind": "score",
                "label": label,
                "prior": None if not old else f"{old.get('win')}/{old.get('odds')}",
                "current": f"{now_win}/{now_odds}",
                "state": state,
            }
        )
    flipped = [row for row in rows if "→" in str(row["state"])]
    lines = [
        "",
        "## 两周对照",
        "",
        f"- 对照周：{prior.get('week_end')} → {current.get('week_end')}",
        "- 本段只记录标签变化，不改立场，也不构成交易授权。",
        "",
    ]
    for row in rows:
        if row["kind"] == "box":
            lines.append(f"- 四格 `{row['label']}`：{row['state']}")
    lines.append("")
    for row in rows:
        if row["kind"] == "score":
            lines.append(f"- 评分 `{row['label']}`：{row['state']}")
    if not flipped:
        lines.append("- 没有四格或评分翻转；默认继续不行动。")
    else:
        names = "、".join(row["label"] for row in flipped)
        lines.append(f"- 发生变化的标签：{names}。变化本身不够成为行动条件。")
    return {"status": "READY", "rows": rows, "markdown": "\n".join(lines) + "\n"}


__all__ = ["build_weekly_compare"]
