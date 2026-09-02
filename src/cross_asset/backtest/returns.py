"""Explicit asset holding-period return semantics for research backtests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AssetReturnSpec:
    """Define how a portfolio asset maps to an observable return series."""

    series_id: str | None
    kind: str = "price"
    duration_years: float | None = None
    annual_rate: float = 0.0
    yield_scale: float = 100.0

    def validate(self) -> None:
        if self.kind not in {"price", "yield_duration_proxy", "cash"}:
            raise ValueError(f"unsupported return kind: {self.kind}")
        if self.kind == "cash":
            if self.series_id is not None:
                raise ValueError("cash return spec must not declare a series_id")
            return
        if not self.series_id:
            raise ValueError(f"{self.kind} return spec requires series_id")
        if self.kind == "yield_duration_proxy":
            if self.duration_years is None or float(self.duration_years) <= 0:
                raise ValueError("yield_duration_proxy requires positive duration_years")
            if float(self.yield_scale) <= 0:
                raise ValueError("yield_scale must be positive")


def _timestamp_utc(value):
    timestamp = pd.Timestamp(value)
    return (
        timestamp.tz_localize("UTC")
        if timestamp.tzinfo is None
        else timestamp.tz_convert("UTC")
    )


def _latest_boundary_row(rows, boundary, available_boundary=None):
    eligible = rows[rows["_date"] <= pd.Timestamp(boundary).date()]
    if available_boundary is not None and "_available" in rows:
        eligible = eligible[eligible["_available"] <= _timestamp_utc(available_boundary)]
    if eligible.empty:
        return None
    sort_columns = ["_date"] + (["_available"] if "_available" in eligible else [])
    return eligible.sort_values(sort_columns).iloc[-1]


def period_asset_return(
    observations: pd.DataFrame,
    *,
    decision,
    next_decision,
    spec: AssetReturnSpec,
) -> float | None:
    """Return the complete PIT-resolved decision-to-next-decision holding return."""

    spec.validate()
    if next_decision is None:
        return None
    start_boundary = pd.Timestamp(decision).date()
    end_boundary = pd.Timestamp(next_decision).date()
    if end_boundary <= start_boundary:
        raise ValueError("next_decision must be after decision")

    if spec.kind == "cash":
        years = (end_boundary - start_boundary).days / 365.25
        return float(spec.annual_rate) * years

    if "series_id" not in observations or "observation_date" not in observations:
        return None
    rows = observations[observations["series_id"] == spec.series_id].copy()
    if rows.empty:
        return None
    rows["_date"] = pd.to_datetime(rows["observation_date"]).dt.date
    if "available_at" in rows:
        rows["_available"] = pd.to_datetime(rows["available_at"], utc=True)

    start_row = _latest_boundary_row(rows, decision, decision)
    end_row = _latest_boundary_row(rows, next_decision, next_decision)
    if start_row is None or end_row is None:
        return None
    if end_row["_date"] <= start_row["_date"]:
        return None

    start_value = float(start_row["value"])
    end_value = float(end_row["value"])
    if spec.kind == "price":
        return None if start_value == 0 else end_value / start_value - 1.0

    start_yield = start_value / float(spec.yield_scale)
    end_yield = end_value / float(spec.yield_scale)
    holding_years = (end_row["_date"] - start_row["_date"]).days / 365.25
    return (
        -float(spec.duration_years) * (end_yield - start_yield)
        + start_yield * holding_years
    )


def return_index_from_series(series: pd.Series, spec: AssetReturnSpec) -> pd.Series:
    """Convert an observable level/yield history to a price-like return index."""

    spec.validate()
    values = pd.Series(series, copy=True, dtype=float).dropna()
    if not values.index.is_monotonic_increasing:
        values = values.sort_index()
    values = values[~values.index.duplicated(keep="last")]
    if values.empty:
        return values
    if spec.kind == "price":
        return values
    if spec.kind == "cash":
        raise ValueError("cash return index requires an explicit date grid")
    if not isinstance(values.index, pd.DatetimeIndex):
        try:
            values.index = pd.to_datetime(values.index)
        except (TypeError, ValueError) as exc:
            raise ValueError("yield return index requires datetime-like index") from exc

    yields = values / float(spec.yield_scale)
    days = values.index.to_series().diff().dt.total_seconds().div(86400.0)
    period_returns = (
        -float(spec.duration_years) * yields.diff()
        + yields.shift(1) * days / 365.25
    )
    growth = 1.0 + period_returns
    growth = growth.where(growth > 0)
    result = pd.Series(index=values.index, dtype=float)
    result.iloc[0] = 1.0
    if len(result) > 1:
        cumulative = growth.iloc[1:].cumprod()
        result.iloc[1:] = cumulative.to_numpy()
    return result.replace([np.inf, -np.inf], np.nan).dropna()


def portfolio_period_return(
    observations: pd.DataFrame,
    allocation: Mapping[str, float],
    decision,
    next_decision,
    *,
    specs: Mapping[str, AssetReturnSpec] | None = None,
) -> float | None:
    """Aggregate strict asset returns; missing non-zero legs make the period unavailable."""

    if next_decision is None:
        return None
    configured = specs or {}
    total = 0.0
    for asset, weight in allocation.items():
        weight = float(weight)
        if abs(weight) <= 1e-15:
            continue
        spec = configured.get(asset, AssetReturnSpec(series_id=asset))
        result = period_asset_return(
            observations,
            decision=decision,
            next_decision=next_decision,
            spec=spec,
        )
        if result is None:
            return None
        total += weight * result
    return total


__all__ = [
    "AssetReturnSpec",
    "period_asset_return",
    "portfolio_period_return",
    "return_index_from_series",
]
