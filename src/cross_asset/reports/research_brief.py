"""Small, traceable research brief for human review.

This module formats supplied structured observations. It does not infer
holdings, fill missing values, or turn signals into recommendations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _fact_line(item: Any) -> str:
    if not isinstance(item, dict):
        return f"- {item!r}"
    label = item.get("label", item.get("name", "未命名字段"))
    value = item.get("value", "未提供")
    unit = item.get("unit") or "单位未提供"
    period = item.get("period", item.get("observation_date", "期间未提供"))
    source = item.get("source", "来源未提供")
    return f"- **{label}**：{value} {unit}；期间：{period}；来源：{source}"


def generate_research_brief(
    *,
    output: str | Path = "artifacts/reports/research_brief.md",
    as_of: Any = None,
    data_cutoff: Any = None,
    sources: Any = None,
    completeness: Any = None,
    limitations: Any = None,
    market_facts: Any = None,
    holdings: Any = None,
    research_question: Any = None,
    supporting_evidence: Any = None,
    counterevidence: Any = None,
    next_check: Any = None,
    decision_record: Any = None,
    computed_signals: Any = None,
) -> Path:
    """Write a descriptive, human-reviewable brief from existing fields."""
    source_text = sources if sources is not None else "来源未提供"
    holding_lines = _items(holdings)
    question = research_question if research_question is not None else "待人工填写"
    support = supporting_evidence if supporting_evidence is not None else "待人工填写"
    counter = counterevidence if counterevidence is not None else "待人工填写"
    check = next_check if next_check is not None else "待人工填写"
    decision = decision_record if decision_record is not None else "不行动记录：待人工填写（本简报不产生交易建议）"

    text = "# 个人研究简报\n\n"
    text += f"- 数据截至（as_of）：{as_of if as_of is not None else '未提供'}\n"
    text += f"- 数据截点（data_cutoff）：{data_cutoff if data_cutoff is not None else '未提供'}\n"
    text += f"- 来源：{source_text}\n"
    text += "- 用途：辅助人工研究；不构成交易建议，也不宣称投资验证完成。\n\n"
    text += "## 数据完整性与限制\n\n"
    text += f"- 完整性：{completeness if completeness is not None else '未提供'}\n"
    text += f"- 缺失与限制：{limitations if limitations is not None else '未提供'}\n\n"
    text += "## 市场事实\n\n"
    facts = _items(market_facts)
    text += "\n".join(_fact_line(item) for item in facts) if facts else "- 未提供结构化市场事实"
    text += "\n\n## 持仓上下文\n\n"
    if holding_lines:
        text += "\n".join(_fact_line(item) for item in holding_lines)
    else:
        text += "- 未提供真实持仓；本简报不推断账户、币种、敞口或推荐。"
    text += "\n\n## 计算信号（模型输出）\n\n"
    signals = _items(computed_signals)
    text += "\n".join(_fact_line(item) for item in signals) if signals else "- 未提供计算信号"
    text += "\n\n## 模型计算信号（非市场事实）\n\n"
    signals = _items(computed_signals)
    text += "\n".join(_fact_line(item) for item in signals) if signals else "- 未提供计算信号"
    text += "\n\n## 人工研究记录\n\n"
    text += f"- 研究问题：{question}\n- 支持证据：{support}\n- 反证/反例：{counter}\n- 下次检查：{check}\n- 人工决定与理由：{decision}\n"

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


__all__ = ["generate_research_brief"]
