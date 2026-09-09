"""Sell-side journal versus the computed four-box.

House views stay human input. This module only records agreement or
conflict. It does not change strategic weights or emit trades.
"""

from __future__ import annotations

from typing import Any

BOX_LABELS = ("增长", "通胀", "流动性", "海外约束")

_FAMILIES: dict[str, tuple[set[str], ...]] = {
    "增长": ({"扩张", "扩张偏平"}, {"走弱", "走弱偏平"}, {"不明", "STALE"}),
    "通胀": ({"抬头"}, {"回落或低位"}, {"分化"}, {"不明", "STALE"}),
    "流动性": ({"松"}, {"紧"}, {"中性"}, {"不明", "STALE"}),
    "海外约束": ({"外部松"}, {"外部紧"}, {"中性"}, {"不明", "STALE"}),
}


def _box_map(boxes: list[dict[str, Any]]) -> dict[str, str]:
    return {str(item.get("label")): str(item.get("value")) for item in boxes}


def _same_family(label: str, computed: str, stated: str) -> bool:
    if computed == stated:
        return True
    for family in _FAMILIES.get(label, ()):
        if computed in family and stated in family:
            return True
    return False


def _check_status(computed: str | None, stated: str | None, label: str) -> str:
    if not stated:
        return "卖方未填"
    if computed in {None, "STALE", "不明"}:
        return "价格层缺失，无法对照"
    if _same_family(label, str(computed), str(stated)):
        return "同意"
    return "对照冲突"


def compare_sell_side(
    boxes: list[dict[str, Any]],
    sell_side: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    computed = _box_map(boxes)
    reviews: list[dict[str, Any]] = []
    for item in sell_side or []:
        house_boxes = item.get("boxes") or {}
        checks = []
        for label in BOX_LABELS:
            status = _check_status(
                computed.get(label),
                house_boxes.get(label),
                label,
            )
            checks.append(
                {
                    "label": label,
                    "computed": computed.get(label),
                    "stated": house_boxes.get(label) or "未填",
                    "status": status,
                }
            )
        conflicts = sum(1 for row in checks if row["status"] == "对照冲突")
        agrees = sum(1 for row in checks if row["status"] == "同意")
        if conflicts:
            agreement = "存在对照冲突"
        elif agrees:
            agreement = "与四格同向"
        else:
            agreement = "仅有主题，未填四格"
        reviews.append(
            {
                "house": item.get("house", "未署名"),
                "date": item.get("date", ""),
                "theme": item.get("theme", ""),
                "stance": item.get("stance", ""),
                "checks": checks,
                "agreement": agreement,
            }
        )
    return reviews


def _rel_value(relatives: list[dict[str, Any]], label: str) -> Any:
    for item in relatives:
        if item.get("label") == label:
            return item.get("value")
    return None


def build_narratives(
    boxes: list[dict[str, Any]],
    relatives: list[dict[str, Any]],
    scorecard: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    box = _box_map(boxes)
    growth = box.get("增长")
    inflation = box.get("通胀")
    liquidity = box.get("流动性")
    external = box.get("海外约束")
    copper_vs_eq = _rel_value(relatives, "铜vsA股一周")
    gold_vs_rates = _rel_value(relatives, "黄金vs美债一周")
    ah = _rel_value(relatives, "A相对H一周")
    weak_growth = growth in {"走弱", "走弱偏平"}
    strong_growth = growth in {"扩张", "扩张偏平"}
    stories = [
        {
            "label": "弱增长 + 松流动性",
            "active": weak_growth and liquidity == "松",
            "note": "利率债胜率通常好于股票；默认仍不行动",
        },
        {
            "label": "增长修复 / 再通胀",
            "active": strong_growth and inflation in {"抬头", "分化"},
            "note": "铜与股票需同向才强化该叙事",
        },
        {
            "label": "外部约束收紧",
            "active": external == "外部紧",
            "note": "黄金与美债方向、美股赔率需一起看",
        },
        {
            "label": "相对价格背离",
            "active": copper_vs_eq == "背离" or gold_vs_rates == "背离",
            "note": f"铜vsA股={copper_vs_eq}；黄金vs美债={gold_vs_rates}",
        },
        {
            "label": "A/H 一周分化",
            "active": isinstance(ah, (int, float)) and abs(float(ah)) >= 0.01,
            "note": f"A相对H一周={ah}",
        },
    ]
    card = {
        item.get("label"): item
        for item in scorecard
        if item.get("label") != "macro_context"
    }
    mixed = 0
    for row in card.values():
        win, odds = row.get("win"), row.get("odds")
        if win == "升" and odds in {"差", "消耗"}:
            mixed += 1
        if win == "降" and odds in {"好", "改善"}:
            mixed += 1
    stories.append(
        {
            "label": "胜率与赔率打架",
            "active": mixed > 0,
            "note": f"{mixed} 个资产胜率与赔率反向，维持不行动",
        }
    )
    return stories


def render_view_markdown(
    reviews: list[dict[str, Any]],
    narratives: list[dict[str, Any]],
) -> str:
    lines = ["", "## 卖方与四格对照", ""]
    if not reviews:
        lines.append("- 未提供本周卖方对照。可填 house / date / stance / theme / boxes。")
    for item in reviews:
        house = item["house"]
        day = item.get("date") or ""
        theme = item.get("theme") or "未填写"
        lines.append(f"- **{house}** {day}：{item.get('agreement')}；主线：{theme}")
        if item.get("stance"):
            lines.append(f"  - 观点：{item['stance']}")
        for check in item.get("checks") or []:
            lines.append(
                f"  - {check['label']}：计算={check['computed']} / "
                f"卖方={check['stated']} / {check['status']}"
            )
    lines += ["", "## 竞争叙事", ""]
    active = [item for item in narratives if item.get("active")]
    if not active:
        lines.append("- 本周没有被四格或相对价格点亮的叙事。")
    for item in active:
        lines.append(f"- **{item['label']}**：{item['note']}")
    inactive = [item["label"] for item in narratives if not item.get("active")]
    if inactive:
        lines.append("- 未点亮：" + "、".join(inactive))
    return "\n".join(lines) + "\n"


__all__ = [
    "BOX_LABELS",
    "build_narratives",
    "compare_sell_side",
    "render_view_markdown",
]
