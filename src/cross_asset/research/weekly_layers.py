"""Sell-side-style overlay for the weekly personal review.

Adds relative prices, a four-box macro state card, and a coarse
win-rate / odds split. Missing overlay series stay missing. Layers
never change strategic weights or emit trade instructions.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from cross_asset.research.weekly_review import Observation


OVERLAY_DEFAULTS = [
    {"series_id": "CN_BOND_2Y", "kind": "yield"},
    {"series_id": "US_GOV_10Y", "kind": "yield"},
    {"series_id": "US_GOV_2Y", "kind": "yield"},
    {"series_id": "CN_DR007", "kind": "yield"},
    {"series_id": "CN_PMI", "kind": "level"},
    {"series_id": "CN_CPI", "kind": "level"},
    {"series_id": "CN_PPI", "kind": "level"},
    {"series_id": "CN_M1", "kind": "level"},
]


def _fact(table: dict[str, Any], series_id: str) -> dict[str, Any] | None:
    for item in table.get("facts") or []:
        if item.get("series_id") == series_id:
            return item
    return None


def _chg(table: dict[str, Any], series_id: str, window: str = "1w") -> float | None:
    item = _fact(table, series_id)
    if not item:
        return None
    return ((item.get("changes") or {}).get(window) or {}).get("value")


def _val(table: dict[str, Any], series_id: str) -> float | None:
    item = _fact(table, series_id)
    if not item:
        return None
    value = item.get("value")
    return None if value is None else float(value)


def overlay_levels(
    rows: list[Observation],
    *,
    week_end_date: date,
    cutoff: datetime,
    specs: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    from cross_asset.research.weekly_review import latest_on_or_before

    out: dict[str, dict[str, Any]] = {}
    for spec in specs or OVERLAY_DEFAULTS:
        series_id = spec["series_id"]
        current = latest_on_or_before(rows, series_id, week_end_date, cutoff)
        out[series_id] = {
            "series_id": series_id,
            "kind": spec.get("kind", "level"),
            "value": None if current is None else current.value,
            "observation_date": None if current is None else current.observation_date.isoformat(),
            "source": "missing" if current is None else current.source,
            "status": "READY" if current is not None else "STALE",
        }
    return out


def _overlay_change(
    rows: list[Observation],
    series_id: str,
    kind: str,
    week_end_date: date,
    cutoff: datetime,
    days: int,
) -> float | None:
    from datetime import timedelta

    from cross_asset.research.weekly_review import latest_on_or_before

    current = latest_on_or_before(rows, series_id, week_end_date, cutoff)
    prior = latest_on_or_before(rows, series_id, week_end_date - timedelta(days=days), cutoff)
    if current is None or prior is None:
        return None
    if kind == "yield":
        return round((current.value - prior.value) * 100.0, 4)
    if prior.value == 0:
        return None
    return round(current.value / prior.value - 1.0, 6)


def build_relative_metrics(table: dict[str, Any], overlay: dict[str, Any]) -> list[dict[str, Any]]:
    cn_1w = _chg(table, "CN_EQ_LARGE", "1w")
    hk_1w = _chg(table, "HK_EQ", "1w")
    us_1w = _chg(table, "US_EQ", "1w")
    gold_1w = _chg(table, "GOLD", "1w")
    copper_1w = _chg(table, "COPPER", "1w")
    cn_bond = _val(table, "CN_BOND_10Y")
    us_10y = overlay.get("US_GOV_10Y", {}).get("value")
    cn_2y = overlay.get("CN_BOND_2Y", {}).get("value")
    us_2y = overlay.get("US_GOV_2Y", {}).get("value")
    us_10y_1w = overlay.get("US_GOV_10Y", {}).get("change_1w")

    return [
        {
            "label": "A相对H一周",
            "value": None if cn_1w is None or hk_1w is None else round(cn_1w - hk_1w, 6),
            "unit": "fraction_spread",
            "note": "正值表示A股一周强于港股",
        },
        {
            "label": "中美10Y利差",
            "value": None if cn_bond is None or us_10y is None else round(float(us_10y) - float(cn_bond), 4),
            "unit": "percentage_points",
            "note": "US_GOV_10Y 减 CN_BOND_10Y",
        },
        {
            "label": "中国2s10s",
            "value": None if cn_bond is None or cn_2y is None else round(float(cn_bond) - float(cn_2y), 4),
            "unit": "percentage_points",
            "note": "CN_BOND_10Y 减 CN_BOND_2Y",
        },
        {
            "label": "美国2s10s",
            "value": None if us_10y is None or us_2y is None else round(float(us_10y) - float(us_2y), 4),
            "unit": "percentage_points",
            "note": "US_GOV_10Y 减 US_GOV_2Y",
        },
        {
            "label": "黄金vs美债一周",
            "value": _sign_agree(gold_1w, us_10y_1w, invert_right=True),
            "unit": "agreement",
            "note": "美债利率下行应对黄金上涨；一致=符合，背离=不符合",
        },
        {
            "label": "铜vsA股一周",
            "value": _sign_agree(copper_1w, cn_1w),
            "unit": "agreement",
            "note": "增长定价是否共振",
        },
        {
            "label": "美股一周",
            "value": us_1w,
            "unit": "fraction",
            "note": "缺测则保持缺失",
        },
    ]


def _sign_agree(left: float | None, right: float | None, invert_right: bool = False) -> str:
    if left is None or right is None:
        return "不可比"
    rhs = -right if invert_right else right
    if left == 0 or rhs == 0:
        return "平"
    return "符合" if (left > 0) == (rhs > 0) else "背离"


def build_macro_boxes(overlay: dict[str, Any]) -> list[dict[str, Any]]:
    pmi = overlay.get("CN_PMI", {}).get("value")
    cpi = overlay.get("CN_CPI", {}).get("value")
    ppi = overlay.get("CN_PPI", {}).get("value")
    dr007_1w = overlay.get("CN_DR007", {}).get("change_1w")
    us_10y_1w = overlay.get("US_GOV_10Y", {}).get("change_1w")
    copper_1m = overlay.get("COPPER_1M")
    m1 = overlay.get("CN_M1", {}).get("value")

    if pmi is None and copper_1m is None:
        growth, growth_note = "STALE", "缺 PMI 与铜的一月窗口"
    elif pmi is not None and pmi >= 50 and (copper_1m is None or copper_1m > 0):
        growth, growth_note = "扩张", f"PMI={pmi}"
    elif pmi is not None and pmi >= 50:
        growth, growth_note = "扩张偏平", f"PMI={pmi}，铜一月未确认"
    elif pmi is not None and pmi < 50 and copper_1m is not None and copper_1m > 0:
        growth, growth_note = "走弱偏平", f"PMI={pmi}，铜一月仍为正"
    elif pmi is not None and pmi < 50:
        growth, growth_note = "走弱", f"PMI={pmi}"
    else:
        growth, growth_note = "不明", "仅有铜、无 PMI"

    if cpi is None and ppi is None:
        inflation, inflation_note = "STALE", "缺 CPI/PPI"
    elif cpi is not None and cpi < 1 and ppi is not None and ppi > 0:
        inflation, inflation_note = "分化", f"CPI={cpi}，PPI={ppi}"
    elif cpi is not None and cpi >= 2:
        inflation, inflation_note = "抬头", f"CPI={cpi}"
    else:
        inflation, inflation_note = "回落或低位", f"CPI={cpi}，PPI={ppi}"

    if dr007_1w is None:
        liquidity = "STALE" if overlay.get("CN_DR007", {}).get("value") is None else "中性"
        liquidity_note = "缺 DR007 一周变化" if dr007_1w is None else f"M1={m1}"
    elif dr007_1w < 0:
        liquidity, liquidity_note = "松", f"DR007一周 {dr007_1w}bp"
    elif dr007_1w > 0:
        liquidity, liquidity_note = "紧", f"DR007一周 {dr007_1w}bp"
    else:
        liquidity, liquidity_note = "中性", "DR007一周持平"

    if us_10y_1w is None:
        external, external_note = "STALE", "缺美债10Y一周"
    elif us_10y_1w > 5:
        external, external_note = "外部紧", f"美债10Y一周 {us_10y_1w}bp"
    elif us_10y_1w < -5:
        external, external_note = "外部松", f"美债10Y一周 {us_10y_1w}bp"
    else:
        external, external_note = "中性", f"美债10Y一周 {us_10y_1w}bp"

    return [
        {"label": "增长", "value": growth, "unit": "state", "source": growth_note},
        {"label": "通胀", "value": inflation, "unit": "state", "source": inflation_note},
        {"label": "流动性", "value": liquidity, "unit": "state", "source": liquidity_note},
        {"label": "海外约束", "value": external, "unit": "state", "source": external_note},
    ]


def _dir(change: float | None, up_label: str = "升", down_label: str = "降", flat: str = "平") -> str:
    if change is None:
        return "不明"
    if change > 0:
        return up_label
    if change < 0:
        return down_label
    return flat


def build_scorecard(table: dict[str, Any], overlay: dict[str, Any], boxes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    box = {item["label"]: item["value"] for item in boxes}
    pmi = overlay.get("CN_PMI", {}).get("value")
    us_10y_1w = overlay.get("US_GOV_10Y", {}).get("change_1w")
    dr007_1w = overlay.get("CN_DR007", {}).get("change_1w")
    cn_1w = _chg(table, "CN_EQ_LARGE", "1w")
    hk_1w = _chg(table, "HK_EQ", "1w")
    us_1w = _chg(table, "US_EQ", "1w")
    gold_1w = _chg(table, "GOLD", "1w")
    copper_1w = _chg(table, "COPPER", "1w")
    copper_1m = _chg(table, "COPPER", "1m")
    bond_level = _val(table, "CN_BOND_10Y")
    bond_1w = _chg(table, "CN_BOND_10Y", "1w")

    def odds_from_pullback(change_1w: float | None, change_1m: float | None) -> str:
        if change_1w is None:
            return "不明"
        if change_1w <= -0.01:
            return "改善"
        if change_1m is not None and change_1m >= 0.05:
            return "消耗"
        return "中"

    rows = [
        {
            "label": "CN_EQ",
            "win": "降" if (pmi is not None and pmi < 50) or (copper_1w is not None and copper_1w < 0) else (
                "升" if (pmi is not None and pmi >= 50) or (copper_1w is not None and copper_1w > 0) else "平"
            ),
            "odds": odds_from_pullback(cn_1w, _chg(table, "CN_EQ_LARGE", "1m")),
            "note": f"1w={cn_1w}",
        },
        {
            "label": "HK_EQ",
            "win": _dir(hk_1w),
            "odds": odds_from_pullback(hk_1w, _chg(table, "HK_EQ", "1m")),
            "note": f"1w={hk_1w}",
        },
        {
            "label": "US_EQ",
            "win": "降" if us_10y_1w is not None and us_10y_1w > 5 else (
                "升" if us_10y_1w is not None and us_10y_1w < -5 else _dir(us_1w)
            ),
            "odds": odds_from_pullback(us_1w, _chg(table, "US_EQ", "1m")),
            "note": f"1w={us_1w}",
        },
        {
            "label": "CN_BOND",
            "win": (
                "不明" if bond_1w is None and dr007_1w is None else
                "升" if (bond_1w is not None and bond_1w < 0) or (bond_1w is None and dr007_1w is not None and dr007_1w < 0) else
                "降" if (bond_1w is not None and bond_1w > 0) or (bond_1w is None and dr007_1w is not None and dr007_1w > 0) else
                "平"
            ),
            "odds": "差" if bond_level is not None and bond_level <= 1.70 else (
                "好" if bond_level is not None and bond_level >= 2.00 else "中"
            ),
            "note": f"level={bond_level} 1w_bp={bond_1w}",
        },
        {
            "label": "GOLD",
            "win": "升" if us_10y_1w is not None and us_10y_1w <= 0 else (
                "降" if us_10y_1w is not None and us_10y_1w > 0 else _dir(gold_1w)
            ),
            "odds": "消耗" if _chg(table, "GOLD", "1m") is not None and _chg(table, "GOLD", "1m") >= 0.05 else "中",
            "note": f"1w={gold_1w}",
        },
        {
            "label": "COPPER",
            "win": "升" if (pmi is not None and pmi >= 50) or (copper_1w is not None and copper_1w > 0) else (
                "降" if copper_1w is not None and copper_1w < 0 else "平"
            ),
            "odds": "消耗" if copper_1m is not None and copper_1m >= 0.05 else "中",
            "note": f"1w={copper_1w}",
        },
    ]
    rows.append(
        {
            "label": "macro_context",
            "win": box.get("增长", "不明"),
            "odds": box.get("流动性", "不明"),
            "note": f"通胀={box.get('通胀')} 海外={box.get('海外约束')}",
        }
    )
    return rows


def decide_stance(scorecard: list[dict[str, Any]]) -> dict[str, Any]:
    leans = []
    for row in scorecard:
        if row["label"] == "macro_context":
            continue
        win, odds = row.get("win"), row.get("odds")
        if win == "升" and odds in {"好", "改善"}:
            leans.append(("偏多观察", row["label"]))
        elif win == "降" and odds in {"差", "消耗"}:
            leans.append(("偏空观察", row["label"]))
    unique = {item[0] for item in leans}
    if not leans:
        stance = "分层不一致，保持观察"
    elif unique == {"偏多观察"} or unique == {"偏空观察"}:
        stance = f"{next(iter(unique))}：{', '.join(item[1] for item in leans)}"
    else:
        stance = "多空同时出现，保持观察"
    return {
        "decision": "不行动",
        "stance": stance,
        "leans": [{"asset": asset, "lean": lean} for lean, asset in leans],
        "rule": "默认不行动；胜率与赔率同向才记倾向，不改战略权重。",
    }


def render_layer_markdown(
    *,
    relatives: list[dict[str, Any]],
    boxes: list[dict[str, Any]],
    scorecard: list[dict[str, Any]],
    stance: dict[str, Any],
    sell_side: list[dict[str, Any]] | None,
) -> str:
    lines = ["", "## 相对价格", ""]
    for item in relatives:
        lines.append(
            f"- **{item['label']}**：{item.get('value')} {item.get('unit')}；{item.get('note')}"
        )
    lines += ["", "## 宏观四格", ""]
    for item in boxes:
        lines.append(f"- **{item['label']}**：{item['value']}；{item.get('source')}")
    lines += ["", "## 胜率 / 赔率", ""]
    for item in scorecard:
        if item["label"] == "macro_context":
            lines.append(f"- **宏观背景**：增长 {item['win']} / 流动性 {item['odds']}；{item['note']}")
            continue
        lines.append(
            f"- **{item['label']}**：胜率 {item['win']} / 赔率 {item['odds']}；{item['note']}"
        )
    lines += ["", "## 决策合同", ""]
    lines.append(f"- 决定：{stance['decision']}")
    lines.append(f"- 倾向：{stance['stance']}")
    lines.append(f"- 规则：{stance['rule']}")
    lines += ["", "## 卖方对照（人工）", ""]
    if sell_side:
        for item in sell_side:
            lines.append(
                f"- **{item.get('house', '未署名')}** {item.get('date', '')}："
                f"{item.get('stance', '')}；主线：{item.get('theme', '未填写')}"
            )
    else:
        lines.append("- 未提供本周卖方对照。字段：house / date / stance / theme。")
    return "\n".join(lines) + "\n"


def build_weekly_layers(
    rows: list[Observation],
    table: dict[str, Any],
    *,
    cutoff: datetime,
    sell_side: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    week_end_date = date.fromisoformat(table["week_end"])
    overlay = overlay_levels(rows, week_end_date=week_end_date, cutoff=cutoff)
    for spec in OVERLAY_DEFAULTS:
        series_id = spec["series_id"]
        overlay[series_id]["change_1w"] = _overlay_change(
            rows, series_id, spec.get("kind", "level"), week_end_date, cutoff, 7
        )
    overlay["COPPER_1M"] = _chg(table, "COPPER", "1m")
    relatives = build_relative_metrics(table, overlay)
    boxes = build_macro_boxes(overlay)
    scorecard = build_scorecard(table, overlay, boxes)
    stance = decide_stance(scorecard)
    return {
        "overlay": overlay,
        "relatives": relatives,
        "macro_boxes": boxes,
        "scorecard": scorecard,
        "stance": stance,
        "sell_side": sell_side or [],
        "markdown": render_layer_markdown(
            relatives=relatives,
            boxes=boxes,
            scorecard=scorecard,
            stance=stance,
            sell_side=sell_side,
        ),
    }


__all__ = [
    "OVERLAY_DEFAULTS",
    "build_macro_boxes",
    "build_relative_metrics",
    "build_scorecard",
    "build_weekly_layers",
    "decide_stance",
]
