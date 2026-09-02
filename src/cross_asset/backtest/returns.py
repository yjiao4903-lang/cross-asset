"""Explicit asset holding-period return semantics for research backtests."""

from collections.abc import Mapping
from dataclasses import dataclass

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


def _date(value):
    return pd.Timestamp(value).date()


def period_asset_return(
    observations: pd.DataFrame,
    *,
    decision,
    next_decision,
    spec: AssetReturnSpec,
) -> float | None:
    """Return the complete decision-to-next-decision holding-period return.

    Price assets use the latest observation on or before each boundary. Yield
    assets use an explicit duration approximation instead of treating yields as
    prices. Missing data is returned as None rather than silently imputed.
    """

    spec.validate()
    if next_decision is None:
        return 0.0
    start_boundary, end_boundary = _date(decision), _date(next_decision)
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
    before = rows[rows["_date"] <= start_boundary].sort_values("_date")
    through_end = rows[rows["_date"] <= end_boundary].sort_values("_date")
    if before.empty or through_end.empty:
        return None

    start_row = before.iloc[-1]
    end_row = through_end.iloc[-1]
    if end_row["_date"] <= start_row["_date"]:
        return None
    start_value, end_value = float(start_row["value"]), float(end_row["value"])

    if spec.kind == "price":
        return None if start_value == 0 else end_value / start_value - 1.0

    start_yield = start_value / float(spec.yield_scale)
    end_yield = end_value / float(spec.yield_scale)
    holding_years = (end_row["_date"] - start_row["_date"]).days / 365.25
    return (
        -float(spec.duration_years) * (end_yield - start_yield)
        + start_yield * holding_years
    )


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
        return 0.0
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


__all__ = ["AssetReturnSpec", "period_asset_return", "portfolio_period_return"]
