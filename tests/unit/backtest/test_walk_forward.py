import pandas as pd
import pytest

from cross_asset.backtest.metrics import performance_metrics
from cross_asset.backtest.walk_forward import (
    build_calendar_window_manifest,
    build_turnover_cost_ledger,
    build_window_manifest,
    cost_sensitivity_ledger,
)

DATES = pd.to_datetime(["2024-01-03", "2024-01-17", "2024-02-02", "2024-02-20", "2024-03-01"])


def test_expanding_manifest_uses_explicit_dates_and_exact_boundaries():
    out = build_window_manifest(DATES, train_size=2, test_size=1)
    assert len(out) == 3
    assert out[0]["train_indices"] == (0, 1)
    assert out[0]["test_indices"] == (2,)
    assert out[0]["train_start"] == DATES[0]
    assert out[0]["train_end"] == DATES[1]
    assert out[0]["test_start"] == DATES[2]
    assert out[-1]["train_indices"] == (0, 1, 2, 3)
    assert out[-1]["test_indices"] == (4,)
    # Irregular gaps are preserved; no inferred weekly dates appear.
    assert [x["test_start"] for x in out] == [DATES[2], DATES[3], DATES[4]]


def test_rolling_manifest_has_fixed_training_width():
    out = build_window_manifest(DATES, rolling_window=2, test_size=1, window_type="rolling")
    assert [x["train_indices"] for x in out] == [(0, 1), (1, 2), (2, 3)]
    assert all(x["window_type"] == "rolling" for x in out)


@pytest.mark.parametrize("bad", [DATES[[0, 2, 1]], DATES[[0, 1, 1, 2]]])
def test_manifest_rejects_unsorted_or_duplicate_dates(bad):
    with pytest.raises(ValueError, match="strictly increasing"):
        build_window_manifest(bad, train_size=1)


def test_rolling_requires_window_and_expanding_defaults_to_one_history_date():
    with pytest.raises(ValueError, match="rolling_window"):
        build_window_manifest(DATES, window_type="rolling")
    out = build_window_manifest(DATES)
    assert out[0]["train_indices"] == (0,)
    assert out[0]["test_indices"] == (1,)


@pytest.mark.parametrize("bps", [0, 10, 30])
def test_cost_ledger_contains_turnover_and_cost_for_supported_levels(bps):
    returns = pd.Series([0.01, 0.02], index=DATES[:2])
    allocations = pd.DataFrame({"A": [1.0, 0.5], "B": [0.0, 0.5]}, index=DATES[:2])
    ledger = build_turnover_cost_ledger(returns, allocations, cost_bps=bps)
    assert list(ledger.index) == list(returns.index)
    assert ledger["turnover"].tolist() == [0.0, 1.0]
    assert ledger["cost"].tolist() == [0.0, bps / 10000]
    assert ledger["net_return"].iloc[1] == pytest.approx(0.02 - bps / 10000)
    assert set(cost_sensitivity_ledger(returns, allocations)) == {0, 5, 10, 20, 30}


def test_cost_ledger_rejects_length_mismatch():
    with pytest.raises(ValueError, match="equal length"):
        build_turnover_cost_ledger(pd.Series([0.01, 0.02]), pd.DataFrame({"A": [1.0]}))


def test_metrics_worst_1m_recovery_and_cost():
    # Four weekly observations are the project's one-month window.
    returns = pd.Series([0.10, -0.20, 0.05, 0.10], index=DATES[:4])
    allocations = pd.DataFrame({"A": [1.0, 0.0, 1.0, 1.0]}, index=DATES[:4])
    metrics = performance_metrics(returns, allocations)
    assert metrics["Worst1M"] == pytest.approx((1.1 * 0.8 * 1.05 * 1.1) - 1)
    assert metrics["Recovery"] == 3
    assert metrics["Cost"] == 0.0

    from cross_asset.backtest.metrics import compare_costs

    result = compare_costs(returns, allocations, cost_bps=10)
    assert result["net"]["Cost"] == pytest.approx(0.002)
    assert result["ledger"]["cost"].sum() == pytest.approx(0.002)



def test_calendar_manifest_honors_year_month_protocol_without_inventing_dates():
    dates = pd.date_range("2018-01-05", "2026-12-25", freq="W-FRI")
    folds = build_calendar_window_manifest(
        dates,
        train_min_years=5,
        test_window_months=12,
        step_months=3,
    )
    assert folds
    first = folds[0]
    assert first["test_start"] >= pd.Timestamp("2023-01-05")
    assert first["train_start"] == dates[0]
    assert first["train_end"] < first["test_start"]
    assert first["test_end"] < first["test_start"] + pd.DateOffset(months=12)
    assert folds[1]["test_start"] >= first["test_start"] + pd.DateOffset(months=3)
    supplied = set(dates)
    assert all(
        fold[key] in supplied
        for fold in folds
        for key in ("train_start", "train_end", "test_start", "test_end")
    )


def test_calendar_rolling_manifest_limits_training_horizon():
    dates = pd.date_range("2015-01-02", "2026-12-25", freq="W-FRI")
    folds = build_calendar_window_manifest(
        dates,
        train_min_years=5,
        test_window_months=12,
        step_months=6,
        window_type="rolling",
        rolling_years=3,
    )
    first = folds[0]
    assert first["window_type"] == "rolling"
    assert first["train_start"] >= first["test_start"] - pd.DateOffset(years=3)


def test_calendar_manifest_rejects_invalid_protocol_lengths():
    with pytest.raises(ValueError, match="positive"):
        build_calendar_window_manifest(DATES, train_min_years=0)
    with pytest.raises(ValueError, match="rolling_years"):
        build_calendar_window_manifest(DATES, window_type="rolling")
