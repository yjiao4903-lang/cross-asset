import pandas as pd

from cross_asset.backtest.benchmarks import static_allocation, trend_only
from cross_asset.backtest.metrics import performance_metrics
from cross_asset.backtest.replay import HistoricalReplay
from cross_asset.reports.daily import generate_daily_report


class Strategy:
    def __init__(self):
        self.calls = []

    def __call__(self, info, decision):
        self.calls.append((decision, info["available_at"].max() if len(info) else None))
        return {"A": 0.5, "B": 0.5}

    def next_return(self, info, allocation, decision):
        # Assert replay supplies only information available at this decision.
        assert info.empty or (pd.to_datetime(info["available_at"]) <= decision).all()
        return 0.01


def _observations():
    return pd.DataFrame(
        [
            {"available_at": "2025-01-03", "observation_date": "2025-01-03", "future": 0},
            {"available_at": "2025-01-10", "observation_date": "2025-01-10", "future": 1},
        ]
    )


def test_replay_is_pit_safe_w_fri_and_deterministic():
    first = Strategy()
    result = HistoricalReplay(_observations(), first, cost_bps=0).run("2025-01-03", "2025-01-17")
    assert len(result.decision_dates) == 3
    assert all(
        available is None or pd.Timestamp(available) <= decision
        for decision, available in first.calls
    )
    second = HistoricalReplay(_observations(), Strategy(), cost_bps=0).run(
        "2025-01-03", "2025-01-17"
    )
    pd.testing.assert_series_equal(result.returns, second.returns)


def test_replay_cost_changes_net_return_and_metrics_boundaries():
    class Rotating(Strategy):
        def __call__(self, info, decision):
            super().__call__(info, decision)
            return {"A": 0.8, "B": 0.2} if len(self.calls) % 2 else {"A": 0.2, "B": 0.8}

    no_cost = HistoricalReplay(_observations(), Rotating(), cost_bps=0).run(
        "2025-01-03", "2025-01-17"
    )
    cost = HistoricalReplay(_observations(), Rotating(), cost_bps=100).run(
        "2025-01-03", "2025-01-17"
    )
    assert cost.returns.sum() < no_cost.returns.sum()
    metrics = performance_metrics(cost.returns, cost.allocations)
    assert metrics["turnover"] >= 0 and metrics["max_drawdown"] <= 0


def test_static_and_trend_only_benchmarks_are_callable():
    weights = static_allocation(None, None, {"A": 1.0})
    assert weights["A"] == 1
    assert trend_only(None, None).empty


def test_daily_report_has_sections_and_offline_source(tmp_path):
    path = generate_daily_report(
        output=tmp_path / "daily.md", as_of="2025-12-31", offline_fixture=True
    )
    text = path.read_text(encoding="utf-8")
    for section in (
        "Market",
        "Macro",
        "Style",
        "Asset",
        "Allocation",
        "Contributions",
        "Signal Conflicts",
        "Data Health",
    ):
        assert f"## {section}" in text
    assert "offline fixture" in text
