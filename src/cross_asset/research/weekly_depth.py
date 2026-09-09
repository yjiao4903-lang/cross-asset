"""Deeper weekly research: transmission, priced-in, falsifiers.

Four-box labels are the newspaper layer. This module asks whether
the implied causal chain actually cleared, what is already in the
price, and what next-week print would kill the active story.
History is optional: percentiles stay blank until enough samples
exist. Nothing here changes strategic weights or emits trades.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

MIN_PERCENTILE_SAMPLES = 20


def _box(boxes: list[dict[str, Any]], label: str) -> str | None:
    for item in boxes:
        if item.get("label") == label:
            value = item.get("value")
            return None if value is None else str(value)
    return None


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


def _sign(value: float | None, dead: float = 0.0) -> int | None:
    if value is None:
        return None
    if value > dead:
        return 1
    if value < -dead:
        return -1
    return 0


def _link(
    *,
    label: str,
    status: str,
    note: str,
    legs: list[str],
) -> dict[str, Any]:
    return {"label": label, "status": status, "note": note, "legs": legs}


def _growth_link(
    pmi: float | None,
    copper_1w: float | None,
    equity_1w: float | None,
) -> dict[str, Any]:
    legs = ["CN_PMI", "COPPER", "CN_EQ_LARGE"]
    pmi_sign = None if pmi is None else (1 if pmi >= 50 else -1)
    copper_sign = _sign(copper_1w)
    equity_sign = _sign(equity_1w)
    signs = [item for item in (pmi_sign, copper_sign, equity_sign) if item is not None]
    if len(signs) < 2:
        return _link(
            label="增长复合体",
            status="样本不足",
            note="PMI / 铜 / A股 至少要有两腿才能判断传导",
            legs=legs,
        )
    if len(set(signs) - {0}) <= 1 and 0 not in set(signs):
        direction = "扩张" if signs[0] > 0 else "走弱"
        return _link(
            label="增长复合体",
            status="接通",
            note=f"PMI/铜/A股同向，走的是{direction}",
            legs=legs,
        )
    return _link(
        label="增长复合体",
        status="断裂",
        note=(
            f"PMI={pmi}，铜一周={copper_1w}，A股一周={equity_1w}；"
            "增长叙事没有被价格完整确认"
        ),
        legs=legs,
    )


def _duration_link(
    dr007_1w: float | None,
    bond_1w: float | None,
) -> dict[str, Any]:
    legs = ["CN_DR007", "CN_BOND_10Y"]
    left = _sign(dr007_1w)
    right = _sign(bond_1w)
    if left is None or right is None:
        return _link(
            label="国内利率传导",
            status="样本不足",
            note="缺 DR007 或国债一周变化",
            legs=legs,
        )
    if left == right and left != 0:
        word = "宽松" if left < 0 else "收紧"
        return _link(
            label="国内利率传导",
            status="接通",
            note=f"资金利率与国债收益率同向，{word}传到了久期",
            legs=legs,
        )
    if left == 0 or right == 0:
        return _link(
            label="国内利率传导",
            status="弱接通",
            note="有一条腿几乎不动，传导不完整",
            legs=legs,
        )
    return _link(
        label="国内利率传导",
        status="断裂",
        note=(
            f"DR007一周={dr007_1w}bp，国债10Y一周={bond_1w}bp；"
            "流动性没有按同向进入长端"
        ),
        legs=legs,
    )


def _gold_link(gold_1w: float | None, us_10y_1w: float | None) -> dict[str, Any]:
    legs = ["GOLD", "US_GOV_10Y"]
    gold_sign = _sign(gold_1w)
    rate_sign = _sign(us_10y_1w)
    if gold_sign is None or rate_sign is None:
        return _link(
            label="黄金-利率对冲",
            status="样本不足",
            note="缺黄金或美债一周变化",
            legs=legs,
        )
    if gold_sign == 0 or rate_sign == 0:
        return _link(
            label="黄金-利率对冲",
            status="弱接通",
            note="黄金或美债几乎横盘，对冲信号弱",
            legs=legs,
        )
    if gold_sign == -rate_sign:
        return _link(
            label="黄金-利率对冲",
            status="接通",
            note="黄金与名义利率反向，利率对冲叙事成立",
            legs=legs,
        )
    return _link(
        label="黄金-利率对冲",
        status="断裂",
        note=(
            f"黄金一周={gold_1w}，美债10Y一周={us_10y_1w}bp；"
            "黄金不在走利率叙事，残差在财政/美元/风险溢价"
        ),
        legs=legs,
    )


def _ah_link(cn_1w: float | None, hk_1w: float | None) -> dict[str, Any]:
    legs = ["CN_EQ_LARGE", "HK_EQ"]
    left = _sign(cn_1w, dead=0.003)
    right = _sign(hk_1w, dead=0.003)
    if left is None or right is None:
        return _link(
            label="A-H 同步",
            status="样本不足",
            note="缺 A 或 H 一周收益",
            legs=legs,
        )
    if left == right and left != 0:
        return _link(
            label="A-H 同步",
            status="接通",
            note="两岸风险资产同向，更像共同风险因子",
            legs=legs,
        )
    if left == 0 or right == 0:
        return _link(
            label="A-H 同步",
            status="弱接通",
            note="一侧横盘，分化还谈不上趋势",
            legs=legs,
        )
    return _link(
        label="A-H 同步",
        status="断裂",
        note=f"A一周={cn_1w}，H一周={hk_1w}；定价因子已经拆开",
        legs=legs,
    )


def _external_link(us_10y_1w: float | None, cn_1w: float | None) -> dict[str, Any]:
    legs = ["US_GOV_10Y", "CN_EQ_LARGE"]
    rate = _sign(us_10y_1w, dead=5.0)
    equity = _sign(cn_1w)
    if us_10y_1w is None or cn_1w is None:
        return _link(
            label="外部利率→A股",
            status="样本不足",
            note="缺美债脉冲或 A 股一周",
            legs=legs,
        )
    if rate == 0:
        return _link(
            label="外部利率→A股",
            status="无脉冲",
            note=f"美债10Y一周仅 {us_10y_1w}bp，外部约束本周不是主驱动",
            legs=legs,
        )
    if rate > 0 and equity is not None and equity < 0:
        return _link(
            label="外部利率→A股",
            status="接通",
            note="美债上行同时 A 股下跌，外部约束传到风险资产",
            legs=legs,
        )
    if rate < 0 and equity is not None and equity > 0:
        return _link(
            label="外部利率→A股",
            status="接通",
            note="美债下行同时 A 股上涨，外部约束放松被买入",
            legs=legs,
        )
    return _link(
        label="外部利率→A股",
        status="断裂",
        note="美债脉冲与 A 股方向不合，A 股走的是国内因子",
        legs=legs,
    )


def build_transmission(
    table: dict[str, Any],
    overlay: dict[str, Any],
) -> list[dict[str, Any]]:
    pmi = overlay.get("CN_PMI", {}).get("value")
    copper_1w = _chg(table, "COPPER")
    cn_1w = _chg(table, "CN_EQ_LARGE")
    gold_1w = _chg(table, "GOLD")
    bond_1w = _chg(table, "CN_BOND_10Y")
    dr007_1w = overlay.get("CN_DR007", {}).get("change_1w")
    us_10y_1w = overlay.get("US_GOV_10Y", {}).get("change_1w")
    return [
        _growth_link(pmi, copper_1w, cn_1w),
        _duration_link(dr007_1w, bond_1w),
        _gold_link(gold_1w, us_10y_1w),
        _ah_link(cn_1w, _chg(table, "HK_EQ")),
        _external_link(us_10y_1w, cn_1w),
    ]


def _curve_shape(level_1w: float | None, curve_1w: float | None) -> str | None:
    if level_1w is None or curve_1w is None:
        return None
    if level_1w > 0 and curve_1w > 0:
        return "熊市变虽"
    if level_1w > 0 and curve_1w < 0:
        return "熊市变平"
    if level_1w < 0 and curve_1w < 0:
        return "牛市变平"
    if level_1w < 0 and curve_1w > 0:
        return "牛市变虽"
    return "横盘"


def build_mechanics(
    table: dict[str, Any],
    overlay: dict[str, Any],
) -> list[dict[str, Any]]:
    cn_10y = _val(table, "CN_BOND_10Y")
    cn_2y = overlay.get("CN_BOND_2Y", {}).get("value")
    us_10y = overlay.get("US_GOV_10Y", {}).get("value")
    us_2y = overlay.get("US_GOV_2Y", {}).get("value")
    cn_10y_1w = _chg(table, "CN_BOND_10Y")
    us_10y_1w = overlay.get("US_GOV_10Y", {}).get("change_1w")
    cn_2y_1w = overlay.get("CN_BOND_2Y", {}).get("change_1w")
    us_2y_1w = overlay.get("US_GOV_2Y", {}).get("change_1w")
    cn_curve = None if cn_10y is None or cn_2y is None else round(cn_10y - cn_2y, 4)
    us_curve = None if us_10y is None or us_2y is None else round(us_10y - us_2y, 4)
    cn_curve_1w = None
    if cn_10y_1w is not None and cn_2y_1w is not None:
        cn_curve_1w = round(cn_10y_1w - cn_2y_1w, 4)
    us_curve_1w = None
    if us_10y_1w is not None and us_2y_1w is not None:
        us_curve_1w = round(us_10y_1w - us_2y_1w, 4)
    gold = _val(table, "GOLD")
    copper = _val(table, "COPPER")
    gold_1w = _chg(table, "GOLD")
    copper_1w = _chg(table, "COPPER")
    ratio = None
    ratio_note = "缺金或铜"
    if gold and copper:
        ratio = round(copper / gold, 6)
        if gold_1w is not None and copper_1w is not None:
            prior_gold = gold / (1 + gold_1w) if gold_1w != -1 else None
            prior_copper = copper / (1 + copper_1w) if copper_1w != -1 else None
            if prior_gold and prior_copper:
                prior_ratio = prior_copper / prior_gold
                delta = round(ratio / prior_ratio - 1, 6)
                tilt = "增长相对避险改善" if delta > 0 else "避险相对增长占优"
                ratio_note = f"一周 {delta}；{tilt}"
    spread = None if us_10y is None or cn_10y is None else round(us_10y - cn_10y, 4)
    spread_1w = None
    if us_10y_1w is not None and cn_10y_1w is not None:
        spread_1w = round(us_10y_1w / 100.0 - cn_10y_1w / 100.0, 4)
    return [
        {
            "label": "中国曲线一周",
            "value": _curve_shape(cn_10y_1w, cn_curve_1w),
            "level": cn_curve,
            "change_bp": cn_curve_1w,
            "note": "用 10Y 一周与 2s10s 一周共同分类",
        },
        {
            "label": "美国曲线一周",
            "value": _curve_shape(us_10y_1w, us_curve_1w),
            "level": us_curve,
            "change_bp": us_curve_1w,
            "note": "用 10Y 一周与 2s10s 一周共同分类",
        },
        {
            "label": "铜金比",
            "value": ratio,
            "note": ratio_note,
        },
        {
            "label": "中美10Y利差一周",
            "value": spread_1w,
            "level": spread,
            "note": "正值表示美债相对中国上行（百分点）",
        },
    ]


def build_priced_residual(
    boxes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    table: dict[str, Any],
) -> list[dict[str, Any]]:
    growth = _box(boxes, "增长")
    liquidity = _box(boxes, "流动性")
    cn_1w = _chg(table, "CN_EQ_LARGE")
    gold_1w = _chg(table, "GOLD")
    by_label = {item["label"]: item for item in links}
    out: list[dict[str, Any]] = []
    growth_link = by_label.get("增长复合体", {})
    if growth in {"走弱", "走弱偏平"}:
        if growth_link.get("status") == "接通" and _sign(cn_1w) == -1:
            out.append(
                {
                    "claim": "弱增长",
                    "state": "已定价",
                    "note": "PMI/铜/A股同向走弱，报纸上的弱增长已经在价格里",
                }
            )
        else:
            out.append(
                {
                    "claim": "弱增长",
                    "state": "残差",
                    "note": "增长标签偏弱，但价格腿没有齐跌，弱增长尚未被完整买入",
                }
            )
    if growth in {"扩张", "扩张偏平"}:
        if growth_link.get("status") == "接通" and _sign(cn_1w) == 1:
            out.append(
                {
                    "claim": "增长修复",
                    "state": "已定价",
                    "note": "扩张标签与铜、A股同向",
                }
            )
        else:
            out.append(
                {
                    "claim": "增长修复",
                    "state": "残差",
                    "note": "标签偏强，价格未齐涨",
                }
            )
    duration = by_label.get("国内利率传导", {})
    if liquidity == "松":
        state = "已定价" if duration.get("status") == "接通" else "残差"
        note = (
            "资金利率下行传到了国债"
            if state == "已定价"
            else "资金松了，但长端没有跟，宽松叙事不完整"
        )
        out.append({"claim": "国内宽松", "state": state, "note": note})
    gold_link = by_label.get("黄金-利率对冲", {})
    if gold_1w is not None:
        if gold_link.get("status") == "接通":
            out.append(
                {
                    "claim": "黄金利率对冲",
                    "state": "已定价",
                    "note": "黄金与美债反向，利率叙事够用",
                }
            )
        elif gold_link.get("status") == "断裂":
            out.append(
                {
                    "claim": "黄金利率对冲",
                    "state": "残差",
                    "note": "黄金与利率同向，不能再用降息交易解释金价",
                }
            )
    ah = by_label.get("A-H 同步", {})
    if ah.get("status") == "断裂":
        out.append(
            {
                "claim": "A-H 共同风险因子",
                "state": "残差",
                "note": "两岸拆开，不能再用单一中国风险资产篮子解释",
            }
        )
    if not out:
        out.append(
            {
                "claim": "本周主叙事",
                "state": "不明",
                "note": "标签与价格都不够，不制造已定价结论",
            }
        )
    return out


def build_falsifiers(
    boxes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    narratives: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    active = [item["label"] for item in narratives if item.get("active")]
    broken = [item["label"] for item in links if item.get("status") == "断裂"]
    out: list[dict[str, Any]] = []
    if "弱增长 + 松流动性" in active:
        out.append(
            {
                "kills": "弱增长 + 松流动性",
                "next_week": (
                    "PMI 回到 50 以上，且铜与 A 股一周同时转正。"
                    "只涨股不涨铜，仍算残差，不算证伪。"
                ),
            }
        )
    if "增长修复 / 再通胀" in active:
        out.append(
            {
                "kills": "增长修复 / 再通胀",
                "next_week": "铜一周转负且 PMI 再次跌破 50。",
            }
        )
    if "相对价格背离" in active or "增长复合体" in broken:
        out.append(
            {
                "kills": "增长复合体断裂",
                "next_week": "铜与 A 股重新同向，连续两周不再打架。",
            }
        )
    if "黄金-利率对冲" in broken:
        out.append(
            {
                "kills": "黄金残差",
                "next_week": (
                    "美债10Y 一周下行且黄金继续涨，残差重新并回利率叙事；"
                    "若利率下行黄金也跌，则残差升级为风险溢价回吐。"
                ),
            }
        )
    if "A-H 同步" in broken or "A/H 一周分化" in active:
        out.append(
            {
                "kills": "A-H 分化",
                "next_week": "两岸一周收益重新同号，且幅度差回到 1% 以内。",
            }
        )
    if not out:
        out.append(
            {
                "kills": "当前不行动",
                "next_week": (
                    "任意一条传导从断裂变成接通，并且该资产胜率与赔率同向。"
                    "单独一条标签翻转不够。"
                ),
            }
        )
    return out


def build_assumptions(
    links: list[dict[str, Any]],
    priced: list[dict[str, Any]],
    stance: dict[str, Any],
) -> list[str]:
    broken = [item["label"] for item in links if item.get("status") == "断裂"]
    residuals = [item["claim"] for item in priced if item.get("state") == "残差"]
    lines = [
        f"决策仍是{stance.get('decision')}，因为胜率/赔率或传导没有同时对齐。"
    ]
    if broken:
        lines.append("承重假设：本周断裂的传导下周不会突然齐步走。断裂=" + "、".join(broken))
    if residuals:
        lines.append("承重假设：残差不会在一周内被价格补齐。残差=" + "、".join(residuals))
    lines.append("承重假设：周六 12:00 北京时间之后才看见的美股/COMEX 修订，不回写本周结论。")
    return lines


def _percentile(values: list[float], current: float) -> float:
    ranked = sorted(values)
    below = sum(1 for item in ranked if item <= current)
    return round(below / len(ranked), 3)


def build_location(
    rows: list[Any],
    table: dict[str, Any],
    overlay: dict[str, Any],
    *,
    cutoff: datetime,
) -> list[dict[str, Any]]:
    from cross_asset.research.weekly_review import to_beijing

    week_end = date.fromisoformat(table["week_end"])
    edge = to_beijing(cutoff)
    specs = [
        ("CN_EQ_LARGE", _val(table, "CN_EQ_LARGE")),
        ("CN_BOND_10Y", _val(table, "CN_BOND_10Y")),
        ("GOLD", _val(table, "GOLD")),
        ("COPPER", _val(table, "COPPER")),
        ("US_GOV_10Y", overlay.get("US_GOV_10Y", {}).get("value")),
    ]
    start = week_end - timedelta(days=370)
    out: list[dict[str, Any]] = []
    for series_id, current in specs:
        if current is None:
            out.append(
                {
                    "series_id": series_id,
                    "percentile_1y": None,
                    "samples": 0,
                    "history_start": None,
                    "history_end": None,
                    "n_unique_periods": 0,
                    "note": "本周缺水平，不估分位",
                }
            )
            continue
        history_by_day = {}
        for row in rows:
            if getattr(row, "series_id", None) != series_id:
                continue
            day = getattr(row, "observation_date", None)
            available = getattr(row, "available_at", None)
            if day is None or available is None:
                continue
            if day < start or day > week_end:
                continue
            if to_beijing(available) > edge:
                continue
            if row.value is None or not math.isfinite(float(row.value)):
                continue
            prior = history_by_day.get(day)
            if prior is None or to_beijing(available) > to_beijing(prior[1]):
                history_by_day[day] = (float(row.value), available)
        history = [item[0] for item in history_by_day.values()]
        history_days = list(history_by_day)
        if len(history) < MIN_PERCENTILE_SAMPLES:
            out.append(
                {
                    "series_id": series_id,
                    "percentile_1y": None,
                    "samples": len(history),
                    "history_start": min(history_days).isoformat() if history_days else None,
                    "history_end": max(history_days).isoformat() if history_days else None,
                    "n_unique_periods": len(history_by_day),
                    "note": "一年样本不足 20，分位留空，避免用三个点假装历史",
                }
            )
            continue
        out.append(
            {
                "series_id": series_id,
                "percentile_1y": _percentile(history, float(current)),
                "samples": len(history),
                "history_start": min(history_days).isoformat() if history_days else None,
                "history_end": max(history_days).isoformat() if history_days else None,
                "n_unique_periods": len(history_by_day),
                "note": "可见样本内的经验分位，不是正式风险模型",
            }
        )
    return out


def render_depth_markdown(
    *,
    links: list[dict[str, Any]],
    mechanics: list[dict[str, Any]],
    priced: list[dict[str, Any]],
    falsifiers: list[dict[str, Any]],
    assumptions: list[str],
    location: list[dict[str, Any]],
) -> str:
    lines = ["", "## 传导图", ""]
    for item in links:
        lines.append(
            f"- **{item['label']}**：{item['status']}；{item['note']}"
        )
    lines += ["", "## 曲线与比价", ""]
    for item in mechanics:
        extra = []
        if item.get("level") is not None:
            extra.append(f"水平={item['level']}")
        if item.get("change_bp") is not None:
            extra.append(f"一周={item['change_bp']}")
        suffix = f"；{'，'.join(extra)}" if extra else ""
        lines.append(
            f"- **{item['label']}**：{item.get('value')}；{item.get('note')}{suffix}"
        )
    lines += ["", "## 已定价 / 残差", ""]
    for item in priced:
        lines.append(f"- **{item['claim']}**：{item['state']}；{item['note']}")
    lines += ["", "## 下周证伪", ""]
    for item in falsifiers:
        lines.append(f"- **推翻「{item['kills']}」**：{item['next_week']}")
    lines += ["", "## 一年位置", ""]
    for item in location:
        pct = item.get("percentile_1y")
        if pct is None:
            lines.append(
                f"- **{item['series_id']}**：分位不可用（n={item['samples']}）；{item['note']}"
            )
        else:
            lines.append(
                f"- **{item['series_id']}**：一年分位 {pct}（n={item['samples']}）"
            )
    lines += ["", "## 承重假设", ""]
    for line in assumptions:
        lines.append(f"- {line}")
    return "\n".join(lines) + "\n"


def build_weekly_depth(
    rows: list[Any],
    table: dict[str, Any],
    *,
    overlay: dict[str, Any],
    boxes: list[dict[str, Any]],
    narratives: list[dict[str, Any]],
    stance: dict[str, Any],
    cutoff: datetime,
) -> dict[str, Any]:
    links = build_transmission(table, overlay)
    mechanics = build_mechanics(table, overlay)
    priced = build_priced_residual(boxes, links, table)
    falsifiers = build_falsifiers(boxes, links, narratives)
    assumptions = build_assumptions(links, priced, stance)
    location = build_location(rows, table, overlay, cutoff=cutoff)
    return {
        "transmission": links,
        "mechanics": mechanics,
        "priced_residual": priced,
        "falsifiers": falsifiers,
        "assumptions": assumptions,
        "location": location,
        "markdown": render_depth_markdown(
            links=links,
            mechanics=mechanics,
            priced=priced,
            falsifiers=falsifiers,
            assumptions=assumptions,
            location=location,
        ),
    }


__all__ = [
    "build_falsifiers",
    "build_mechanics",
    "build_priced_residual",
    "build_transmission",
    "build_weekly_depth",
]
