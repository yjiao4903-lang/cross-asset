import pandas as pd

from cross_asset.backtest.metrics import compare_costs, performance_metrics
from cross_asset.reports.backtest import generate_backtest_report


def test_empty_metrics_safe():
    m = performance_metrics(pd.Series(dtype=float))
    assert m["CAGR"] is None and m["turnover"] == 0


def test_cost_reduces_return_and_report(tmp_path):
    idx = pd.date_range("2025-01-03", periods=3, freq="W-FRI")
    r = pd.Series([0.1, 0.0, 0.1], index=idx)
    a = pd.DataFrame({"A": [1.0, 0.0, 1.0]}, index=idx)
    x = compare_costs(r, a, 100)
    assert x["net"]["CAGR"] < x["gross"]["CAGR"]
    p = generate_backtest_report({"STATIC": x}, output=tmp_path / "r.md")
    assert p.exists() and "offline fixture" in p.read_text()
