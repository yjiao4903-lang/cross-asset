from pathlib import Path

from cross_asset.reports.research_brief import generate_research_brief


def test_research_brief_discloses_missing_holdings():
    path_out = Path("tests/.research_brief_test.md")
    path = generate_research_brief(
        output=path_out,
        as_of="2026-09-09",
        data_cutoff="2026-09-08T16:00:00Z",
        sources=["fixture:macro"],
        market_facts=[{"label": "CPI", "value": 3.0, "unit": "%", "period": "2026-08", "source": "fixture"}],
        computed_signals=[{"label": "Equity score", "value": 0.4, "unit": "score", "period": "2026-09-09", "source": "computed"}],
    )
    text = path.read_text(encoding="utf-8")
    assert "未提供真实持仓" in text
    assert "不构成交易建议" in text
    assert "CPI" in text and "来源：fixture" in text
    assert "模型计算信号" in text and "Equity score" in text
    path.unlink(missing_ok=True)
