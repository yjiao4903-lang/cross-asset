"""Pick this week's story from ranked moves and sleeve jobs.

Institutional notes lead with one thesis, then evidence. This module
ranks the six personal series, maps each sleeve to an environment
job, and writes HOLD-because / flip-if. It does not change weights.
"""

from __future__ import annotations

from typing import Any


SLEEVES: tuple[dict[str, str], ...] = (
    {
        "series_id": "CN_EQ_LARGE",
        "name": "A股",
        "job": "国内增长风险",
        "env": "增长好于预期",
    },
    {
        "series_id": "HK_EQ",
        "name": "港股",
        "job": "离岸中国风险",
        "env": "增长好于预期，并吃外部流动性",
    },
    {
        "series_id": "US_EQ",
        "name": "美股",
        "job": "全球风险资产",
        "env": "增长好于预期",
    },
    {
        "series_id": "CN_BOND_10Y",
        "name": "中国利率债",
        "job": "国内久期",
        "env": "增长或通肨弱于预期",
        "kind": "yield",
    },
    {
        "series_id": "GOLD",
        "name": "黄金",
        "job": "避险与财政残差",
        "env": "增长弱，或通肨/财政超预期",
    },
    {
        "series_id": "COPPER",
        "name": "铜",
        "job": "工业周期",
        "env": "增长或通肨好于预期",
    },
)


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


def _box(boxes: list[dict[str, Any]], label: str) -> str:
    for item in boxes:
        if item.get("label") == label:
            return str(item.get("value") or "不明")
    return "不明"


def _link(depth: dict[str, Any], label: str) -> str:
    for item in depth.get("transmission") or []:
        if item.get("label") == label:
            return str(item.get("status") or "")
    return ""


def _fmt_move(value: float | None, kind: str) -> str:
    if value is None:
        return "缺失"
    if kind == "yield":n        return f"{value:+.1f}bp"
    return f"{value * 100:+.2f}%"


def _score(value: float | None, kind: str) -> float:
    if value is None:
        return 0.0
    if kind == "yield":
        return abs(value) / 5.0
    return abs(value) * 100.0


def rank_moves(table: dict[str, Any]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for spec in SLEEVES:
        series_id = spec["series_id"]
        kind = spec.get("kind", "price")
        move = _chg(table, series_id)
        ranked.append(
            {
                "series_id": series_id,
                "name": spec["name"],
                "job": spec["job"],
                "env": spec["env"],
                "kind": kind,
                "move": move,
                "move_text": _fmt_move(move, kind),
                "score": round(_score(move, kind), 3),
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def _sign(value: float | None, dead: float = 0.0) -> int | None:
    if value is None:
        return None
    if value > dead:
        return 1
    if value < -dead:
        return -1
    return 0


def pick_thesis(
    table: dict[str, Any],
    boxes: list[dict[str, Any]],
    depth: dict[str, Any],
    ranked: list[dict[str, Any]],
) -> dict[str, str]:
    cn = _chg(table, "CN_EQ_LARGE")
    hk = _chg(table, "HK_EQ")
    us = _chg(table, "US_EQ")
    gold = _chg(table, "GOLD")
    copper = _chg(table, "COPPER")
    bond = _chg(table, "CN_BOND_10Y")
    bond_level = _val(table, "CN_BOND_10Y")
    growth = _box(boxes, "增长")
    liquidity = _box(boxes, "流动性")
    growth_link = _link(depth, "增长复合体")
    gold_link = _link(depth, "黄金-利率对冲")
    duration = _link(depth, "国内利率传导")
    ah = _link(depth, "A-H 同步")
    lead = ranked[0]["name"] if ranked else "价格"
    lead_move = ranked[0]["move_text"] if ranked else "不明"

    if ah == "断裂" or (
        _sign(cn, 0.003) is not None
        and _sign(hk, 0.003) is not None
        and _sign(cn, 0.003) != _sign(hk, 0.003)
    ):
        return {
            "id": "ah_split",
            "headline": (
                f"本周不是全球风险齐跌，是A/H拆开："
                f"A股{_fmt_move(cn, 'price')}，港股{_fmt_move(hk, 'price')}。"
            ),
            "why": "共同中国风险篮子这周解释不了价格。",
        }
    if gold_link == "断裂" or (
        _sign(gold) == 1 and _link(depth, "黄金-利率对冲") != "接通"
    ):
        return {
            "id": "gold_residual",
            "headline": (
                f"黄金{_fmt_move(gold, 'price')}，但利率对冲腿是断裂的，"
                "金价不能再写成降息交易。"
            ),
            "why": "残差在财政、美元或风险溢价，不在名义利率。",
        }
    if growth in {"走弱", "走弱偏平"} and growth_link != "接通":
        return {
            "id": "weak_growth_residual",
            "headline": (
                f"增长标签是{growth}，但铜{_fmt_move(copper, 'price')}、"
                f"A股{_fmt_move(cn, 'price')}没有齐跌，弱增长仍是残差。"
            ),
            "why": "报纸上的弱增长还没有被完整买入。",
        }
    if liquidity == "松" and duration == "接通" and bond_level is not None:
        return {
            "id": "easing_priced",
            "headline": (
                f"国内宽松已经传到国债（一周{_fmt_move(bond, 'yield')}），"
                f"但10Y在{bond_level:.2f}，赔率不够加久期。"
            ),
            "why": "胜率好、赔率差时，宽松不是行动指令。",
        }
    if _sign(us, 0.005) == _sign(cn, 0.005) and _sign(cn, 0.005) is not None:
        side = "买入" if _sign(cn) == 1 else "卖出"
        return {
            "id": "global_risk",
            "headline": (
                f"A股与美股同向{side}，更像共同风险因子，"
                f"而不是国内独自定价。"
            ),
            "why": "外部约束这周可能是主驱动。",
        }
    return {
        "id": "lead_print",
        "headline": f"本周最大打印是{lead} {lead_move}，其余腿没有对齐。",
        "why": "单腿波动不够改立场。",
    }


def describe_sleeves(
    ranked: list[dict[str, Any]],
    depth: dict[str, Any],
) -> list[dict[str, Any]]:
    gold_link = _link(depth, "黄金-利率对冲")
    growth_link = _link(depth, "增长复合体")
    duration = _link(depth, "国内利率传导")
    ah = _link(depth, "A-H 同步")
    notes = {
        "CN_EQ_LARGE": (
            "增长复合体未接通，A股这周没有完成增长风险的定价。"
            if growth_link == "断裂"
            else "按国内增长风险腿阅读。"
        ),
        "HK_EQ": (
            "与A股拆开，离岸腿在走自己的流动性/结构。"
            if ah == "断裂"
            else "与A股同向时，更像共同中国风险。"
        ),
        "US_EQ": "全球风险对照腿；小波动时不当成主驱动。",
        "CN_BOND_10Y": (
            "宽松已进长端，但水平决定赔率。"
            if duration == "接通"
            else "资金腿与长端不同向时，不能写加久期。"
        ),
        "GOLD": (
            "利率对冲断裂，黄金这周做的是残差腿。"
            if gold_link == "断裂"
            else "若与美债反向，才算完成避险工作。"
        ),
        "COPPER": (
            "工业周期腿与A股打架，增长定价不完整。"
            if growth_link == "断裂"
            else "与股票同向时，强化增长环境。"
        ),
    }
    out = []
    for item in ranked:
        move = item["move"]
        if move is None:
            did = "缺测"
        elif item["kind"] == "yield":
            did = "收益率下行，久期赚钱" if move < 0 else "收益率上行，久期亏钱"
            if move == 0:
                did = "横盘"
        elif move > 0:
            did = "上涨"
        elif move < 0:
            did = "下跌"
        else:
            did = "横盘"
        out.append(
            {
                "series_id": item["series_id"],
                "name": item["name"],
                "job": item["job"],
                "env": item["env"],
                "move_text": item["move_text"],
                "did": did,
                "note": notes.get(item["series_id"], ""),
            }
        )
    return out


def hold_because(
    stance: dict[str, Any],
    depth: dict[str, Any],
    scorecard: list[dict[str, Any]],
    thesis: dict[str, str],
) -> dict[str, str]:
    mixed = 0
    for row in scorecard:
        if row.get("label") == "macro_context":
            continue
        win, odds = row.get("win"), row.get("odds")
        if win == "升" and odds in {"差", "消耗"}:
            mixed += 1
        if win == "降" and odds in {"好", "改善"}:
            mixed += 1
    broken = [
        item.get("label")
        for item in depth.get("transmission") or []
        if item.get("status") == "断裂"
    ]
    residuals = [
        item.get("claim")
        for item in (depth.get("priced") or depth.get("priced_residual") or [])
        if item.get("state") == "残差"
    ]
    falsifiers = depth.get("falsifiers") or []
    flip = "任意一条传导接通且该资产胜率与赔率同向。"
    if falsifiers:
        first = falsifiers[0]
        flip = f"{first.get('kills')}：{first.get('next_week')}"
    reasons = [thesis["why"]]
    if mixed:
        reasons.append(f"{mixed}个资产胜率与赔率反向。")
    if broken:
        reasons.append("断裂=" + "、".join(str(item) for item in broken))
    if residuals:
        reasons.append("残差=" + "、".join(str(item) for item in residuals))
    decision = stance.get("decision") or "不行动"
    return {
        "decision": str(decision),
        "because": " ".join(reasons),
        "flip_if": flip,
    }


def render_story_markdown(
    thesis: dict[str, str],
    ranked: list[dict[str, Any]],
    sleeves: list[dict[str, Any]],
    hold: dict[str, str],
) -> str:
    lines = [
        "",
        "## 本周主线",
        "",
        f"- {thesis['headline']}",
        f"- 为什么是这条：{thesis['why']}",
        "",
        "## 本周打印（按幅度）",
        "",
    ]
    for item in ranked:
        lines.append(f"- {item['name']} {item['move_text']}")
    lines += ["", "## 持仓腿在做什么", ""]
    for item in sleeves:
        lines.append(
            f"- **{item['name']}**（{item['job']}）："
            f"{item['did']} {item['move_text']}。{item['note']}"
        )
    lines += [
        "",
        "## 为什么仍不行动",
        "",
        f"- 决定：{hold['decision']}",
        f"- 因为：{hold['because']}",
        f"- 下周什么情况下才重看：{hold['flip_if']}",
        "",
    ]
    return "\n".join(lines)


def build_weekly_story(
    *,
    table: dict[str, Any],
    boxes: list[dict[str, Any]],
    scorecard: list[dict[str, Any]],
    stance: dict[str, Any],
    depth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    depth = depth or {}
    ranked = rank_moves(table)
    thesis = pick_thesis(table, boxes, depth, ranked)
    sleeves = describe_sleeves(ranked, depth)
    hold = hold_because(stance, depth, scorecard, thesis)
    return {
        "status": "READY",
        "thesis": thesis,
        "ranked": ranked,
        "sleeves": sleeves,
        "hold": hold,
        "headline": thesis["headline"],
        "markdown": render_story_markdown(thesis, ranked, sleeves, hold),
    }


__all__ = ["SLEEVES", "build_weekly_story", "rank_moves", "pick_thesis"]
