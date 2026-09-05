"""Explicit asset holding-period return semantics for research backtests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

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
    accounting: Mapping[str, Any] | None = None

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


def _embedded_accounting_policy(
    configured: Mapping[str, AssetReturnSpec],
    assets: list[str],
):
    from .accounting import (
        AssetAccountingSpec,
        FXConversionSpec,
        PortfolioAccountingPolicy,
    )

    payloads = {asset: configured[asset].accounting for asset in assets}
    if not any(payloads.values()):
        return None
    if any(payload is None for payload in payloads.values()):
        raise ValueError("accounting_policy_must_cover_all_nonzero_assets")
    typed_payloads = {asset: dict(payload or {}) for asset, payload in payloads.items()}
    reporting = {str(payload.get("reporting_currency")) for payload in typed_payloads.values()}
    versions = {str(payload.get("policy_version")) for payload in typed_payloads.values()}
    supported_values = {
        tuple(str(x) for x in payload.get("supported_currencies", ()))
        for payload in typed_payloads.values()
    }
    pricing = {str(payload.get("pricing_basis")) for payload in typed_payloads.values()}
    semantics = {str(payload.get("performance_semantics")) for payload in typed_payloads.values()}
    if not all(len(values) == 1 for values in (reporting, versions, supported_values, pricing, semantics)):
        raise ValueError("embedded_accounting_policy_inconsistent")

    asset_specs = {}
    for asset, payload in typed_payloads.items():
        fx_raw = payload.get("fx")
        fx = None
        if isinstance(fx_raw, Mapping):
            fx = FXConversionSpec(
                series_id=str(fx_raw["series_id"]),
                local_currency=str(fx_raw["local_currency"]),
                reporting_currency=str(fx_raw["reporting_currency"]),
                quote_direction=str(fx_raw["quote_direction"]),
                max_age_hours=float(fx_raw["max_age_hours"]),
            )
        asset_specs[asset] = AssetAccountingSpec(
            local_currency=str(payload["local_currency"]),
            return_type=str(payload["return_type"]),
            hedge_status=str(payload.get("hedge_status", "UNHEDGED")),
            fx_mapping_status=str(payload.get("fx_mapping_status", "UNRESOLVED")),
            fx=fx,
            hedge_return_series_id=(
                None
                if payload.get("hedge_return_series_id") in (None, "")
                else str(payload["hedge_return_series_id"])
            ),
            futures_roll_semantics=(
                None
                if payload.get("futures_roll_semantics") in (None, "")
                else str(payload["futures_roll_semantics"])
            ),
        )
    policy = PortfolioAccountingPolicy(
        version=next(iter(versions)),
        reporting_currency=next(iter(reporting)),
        supported_currencies=next(iter(supported_values)),
        assets=asset_specs,
        pricing_basis=next(iter(pricing)),
        performance_semantics=next(iter(semantics)),
    )
    policy.validate()
    return policy


def portfolio_asset_returns(
    observations: pd.DataFrame,
    allocation: Mapping[str, float],
    decision,
    next_decision,
    *,
    specs: Mapping[str, AssetReturnSpec] | None = None,
) -> dict[str, float] | None:
    """Resolve holding returns for every non-zero portfolio leg.

    Specs without embedded accounting metadata retain the historical local-return
    utility behavior. Once any non-zero leg carries a D2 accounting contract,
    every non-zero leg must carry the same policy and the result is converted to
    the explicit reporting currency through the shared fail-closed accounting
    function.
    """

    if next_decision is None:
        return None
    configured = specs or {}
    nonzero_assets = [
        str(asset) for asset, weight in allocation.items() if abs(float(weight)) > 1e-15
    ]
    resolved: dict[str, float] = {}
    for asset in nonzero_assets:
        spec = configured.get(asset, AssetReturnSpec(series_id=asset))
        result = period_asset_return(
            observations,
            decision=decision,
            next_decision=next_decision,
            spec=spec,
        )
        if result is None or not np.isfinite(float(result)):
            return None
        resolved[asset] = float(result)

    policy = _embedded_accounting_policy(configured, nonzero_assets)
    if policy is None:
        return resolved
    from .accounting import portfolio_reporting_currency_return

    accounting = portfolio_reporting_currency_return(
        observations,
        allocation,
        decision,
        next_decision,
        return_specs=configured,
        policy=policy,
    )
    return accounting.asset_returns if accounting.resolved else None


def portfolio_period_return(
    observations: pd.DataFrame,
    allocation: Mapping[str, float],
    decision,
    next_decision,
    *,
    specs: Mapping[str, AssetReturnSpec] | None = None,
) -> float | None:
    """Aggregate strict asset returns; missing non-zero legs make the period unavailable."""

    asset_returns = portfolio_asset_returns(
        observations,
        allocation,
        decision,
        next_decision,
        specs=specs,
    )
    if asset_returns is None:
        return None
    return sum(float(allocation[asset]) * value for asset, value in asset_returns.items())


__all__ = [
    "AssetReturnSpec",
    "period_asset_return",
    "portfolio_asset_returns",
    "portfolio_period_return",
    "return_index_from_series",
]
