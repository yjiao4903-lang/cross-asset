"""Leakage-aware OOS return stitching and paired benchmark evaluation."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def stitch_oos_returns(frame: pd.DataFrame, plan: dict) -> pd.DataFrame:
    """Validate fold membership and select one latest-trained observation per date/benchmark."""

    required = {"fold", "decision_date", "benchmark", "net_return"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"oos_return_columns_missing:{sorted(missing)}")
    if plan.get("holdout_sealed") is not True:
        raise ValueError("walk_forward_stitch_requires_sealed_holdout")

    folds = {int(item["fold"]): item for item in plan.get("folds", [])}
    rows = frame.copy()
    rows["decision_date"] = pd.to_datetime(rows["decision_date"], utc=True)
    for row in rows.itertuples(index=False):
        fold = folds.get(int(row.fold))
        if fold is None:
            raise ValueError(f"unknown_fold:{row.fold}")
        start = pd.Timestamp(fold["test_start"])
        end = pd.Timestamp(fold["test_end"])
        when = pd.Timestamp(row.decision_date)
        if not start <= when <= end:
            raise ValueError(f"decision_outside_fold_test_window:{row.fold}:{when.isoformat()}")
        holdout_start = plan.get("holdout_start")
        if holdout_start is not None and when >= pd.Timestamp(holdout_start):
            raise ValueError("sealed_holdout_return_detected")

    rows = rows.sort_values(["decision_date", "benchmark", "fold"])
    return rows.drop_duplicates(["decision_date", "benchmark"], keep="last").reset_index(drop=True)


def _cagr(returns: pd.Series, periods_per_year: int) -> float | None:
    values = returns.dropna().astype(float)
    if values.empty:
        return None
    wealth = float((1.0 + values).prod())
    years = len(values) / periods_per_year
    return wealth ** (1.0 / years) - 1.0 if years > 0 and wealth > 0 else None


def _max_drawdown(returns: pd.Series) -> float | None:
    values = returns.dropna().astype(float)
    if values.empty:
        return None
    wealth = (1.0 + values).cumprod()
    return float((wealth / wealth.cummax() - 1.0).min())


def paired_oos_metrics(
    model_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    periods_per_year: int = 52,
) -> dict:
    aligned = pd.concat(
        [
            pd.Series(model_returns, dtype=float).rename("model"),
            pd.Series(benchmark_returns, dtype=float).rename("benchmark"),
        ],
        axis=1,
        join="inner",
    ).dropna()
    excess = aligned["model"] - aligned["benchmark"]
    tracking_error = (
        float(excess.std(ddof=1) * math.sqrt(periods_per_year))
        if len(excess) > 1
        else None
    )
    annualized_excess = float(excess.mean() * periods_per_year) if len(excess) else None
    information_ratio = (
        annualized_excess / tracking_error
        if tracking_error not in (None, 0.0) and annualized_excess is not None
        else None
    )
    model_dd = _max_drawdown(aligned["model"])
    benchmark_dd = _max_drawdown(aligned["benchmark"])
    return {
        "observations": len(aligned),
        "model_cagr": _cagr(aligned["model"], periods_per_year),
        "benchmark_cagr": _cagr(aligned["benchmark"], periods_per_year),
        "annualized_excess_return": annualized_excess,
        "tracking_error": tracking_error,
        "information_ratio": information_ratio,
        "excess_hit_rate": float((excess > 0).mean()) if len(excess) else None,
        "model_max_drawdown": model_dd,
        "benchmark_max_drawdown": benchmark_dd,
        "drawdown_penalty": (
            abs(model_dd) - abs(benchmark_dd)
            if model_dd is not None and benchmark_dd is not None
            else None
        ),
    }


def verdict_from_thresholds(metrics: dict, thresholds: dict) -> dict:
    checks = {
        "min_oos_observations": (
            metrics.get("observations") is not None
            and metrics["observations"] >= int(thresholds["min_oos_observations"])
        ),
        "min_information_ratio_vs_static": (
            metrics.get("information_ratio") is not None
            and metrics["information_ratio"]
            >= float(thresholds["min_information_ratio_vs_static"])
        ),
        "min_annualized_excess_return_vs_static": (
            metrics.get("annualized_excess_return") is not None
            and metrics["annualized_excess_return"]
            >= float(thresholds["min_annualized_excess_return_vs_static"])
        ),
        "max_drawdown_penalty_vs_static": (
            metrics.get("drawdown_penalty") is not None
            and metrics["drawdown_penalty"]
            <= float(thresholds["max_drawdown_penalty_vs_static"])
        ),
    }
    if not checks["min_oos_observations"]:
        verdict = "INCONCLUSIVE"
    elif all(checks.values()):
        verdict = "ACCEPT"
    else:
        verdict = "REJECT"
    return {"verdict": verdict, "checks": checks}


__all__ = ["paired_oos_metrics", "stitch_oos_returns", "verdict_from_thresholds"]
