"""Fail-closed reporting-currency return accounting for research/backtest paths.

This module deliberately does not perform source admission; formal callers must
supply observations already admitted by the common #18 query. It only adds the
#19-D2 economic accounting contract on top of those rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from cross_asset.operations.execution_timing import (
    RESEARCH_PROXY_PERFORMANCE_SEMANTICS,
    RESEARCH_PROXY_RETURN_TIMING_BASIS,
)

from .returns import AssetReturnSpec, period_asset_return

_SUPPORTED_HEDGE = {"UNHEDGED", "HEDGED"}
_SUPPORTED_FX_DIRECTIONS = {"reporting_per_local", "local_per_reporting"}
_SUPPORTED_MAPPING_STATUS = {"NOT_REQUIRED", "RESOLVED", "UNRESOLVED"}
_SUPPORTED_RETURN_TYPES = {
    "PRICE_RETURN",
    "TOTAL_RETURN",
    "BOND_YIELD_DURATION_PROXY",
    "FUTURES_CONTINUOUS_ROLL_PROXY",
    "CASH_RATE",
    "UNRESOLVED",
}
_BLOCKED_QUALITIES = {"stale", "failed", "unknown", "bad", "missing", "unapproved"}


@dataclass(frozen=True)
class FXConversionSpec:
    series_id: str
    local_currency: str
    reporting_currency: str
    quote_direction: str
    max_age_hours: float

    def validate(self) -> None:
        if not self.series_id:
            raise ValueError("fx_series_id_required")
        if self.quote_direction not in _SUPPORTED_FX_DIRECTIONS:
            raise ValueError("fx_quote_direction_invalid")
        if self.local_currency == self.reporting_currency:
            raise ValueError("fx_not_required_for_same_currency")
        if self.max_age_hours <= 0:
            raise ValueError("fx_max_age_hours_must_be_positive")


@dataclass(frozen=True)
class AssetAccountingSpec:
    local_currency: str
    return_type: str
    hedge_status: str = "UNHEDGED"
    fx_mapping_status: str = "UNRESOLVED"
    fx: FXConversionSpec | None = None
    hedge_return_series_id: str | None = None
    futures_roll_semantics: str | None = None

    def validate(self, reporting_currency: str, supported_currencies: set[str]) -> None:
        if self.local_currency not in supported_currencies:
            raise ValueError(f"unsupported_asset_currency:{self.local_currency}")
        if self.return_type not in _SUPPORTED_RETURN_TYPES:
            raise ValueError(f"return_type_invalid:{self.return_type}")
        if self.hedge_status not in _SUPPORTED_HEDGE:
            raise ValueError(f"hedge_status_invalid:{self.hedge_status}")
        if self.fx_mapping_status not in _SUPPORTED_MAPPING_STATUS:
            raise ValueError(f"fx_mapping_status_invalid:{self.fx_mapping_status}")
        if self.local_currency == reporting_currency:
            if self.fx is not None or self.fx_mapping_status != "NOT_REQUIRED":
                raise ValueError("same_currency_fx_mapping_must_be_not_required")
        elif self.fx is not None:
            self.fx.validate()
            if self.fx_mapping_status != "RESOLVED":
                raise ValueError("configured_fx_mapping_must_be_resolved")
            if (
                self.fx.local_currency != self.local_currency
                or self.fx.reporting_currency != reporting_currency
            ):
                raise ValueError("fx_currency_pair_mismatch")


@dataclass(frozen=True)
class PortfolioAccountingPolicy:
    version: str
    reporting_currency: str
    supported_currencies: tuple[str, ...]
    assets: Mapping[str, AssetAccountingSpec]
    pricing_basis: str = RESEARCH_PROXY_RETURN_TIMING_BASIS
    performance_semantics: str = RESEARCH_PROXY_PERFORMANCE_SEMANTICS

    def validate(self) -> None:
        supported = set(self.supported_currencies)
        if not self.version:
            raise ValueError("accounting_policy_version_required")
        if self.reporting_currency not in supported:
            raise ValueError("reporting_currency_not_supported")
        if not self.assets:
            raise ValueError("accounting_assets_required")
        if self.performance_semantics != RESEARCH_PROXY_PERFORMANCE_SEMANTICS:
            raise ValueError("realizable_performance_claim_not_authorized")
        for spec in self.assets.values():
            spec.validate(self.reporting_currency, supported)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def required_series_ids(self) -> set[str]:
        result: set[str] = set()
        for spec in self.assets.values():
            if spec.fx is not None:
                result.add(spec.fx.series_id)
            if spec.hedge_return_series_id:
                result.add(spec.hedge_return_series_id)
        return result


@dataclass(frozen=True)
class ReturnAccountingResult:
    status: str
    reporting_currency: str
    gross_return: float | None
    asset_returns: dict[str, float]
    local_asset_returns: dict[str, float]
    by_asset: dict[str, dict[str, Any]]
    blockers: tuple[str, ...]
    pricing_start_at: Any
    pricing_end_at: Any
    fx_start_at: Any
    fx_end_at: Any
    return_timing_basis: str
    performance_semantics: str

    @property
    def resolved(self) -> bool:
        return self.status == "RESOLVED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fx_from_mapping(raw: Mapping[str, Any] | None) -> FXConversionSpec | None:
    if raw is None:
        return None
    return FXConversionSpec(
        series_id=str(raw["series_id"]),
        local_currency=str(raw["local_currency"]),
        reporting_currency=str(raw["reporting_currency"]),
        quote_direction=str(raw["quote_direction"]),
        max_age_hours=float(raw["max_age_hours"]),
    )


def load_return_accounting_policy(
    path: str | Path = "config/return_accounting.yml",
) -> PortfolioAccountingPolicy:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("return_accounting_config_must_be_mapping")
    assets_raw = raw.get("assets")
    if not isinstance(assets_raw, dict):
        raise TypeError("return_accounting_assets_must_be_mapping")
    assets = {
        str(asset): AssetAccountingSpec(
            local_currency=str(spec["local_currency"]),
            return_type=str(spec["return_type"]),
            hedge_status=str(spec.get("hedge_status", "UNHEDGED")),
            fx_mapping_status=str(spec.get("fx_mapping_status", "UNRESOLVED")),
            fx=_fx_from_mapping(spec.get("fx")),
            hedge_return_series_id=(
                None
                if spec.get("hedge_return_series_id") in (None, "")
                else str(spec["hedge_return_series_id"])
            ),
            futures_roll_semantics=(
                None
                if spec.get("futures_roll_semantics") in (None, "")
                else str(spec["futures_roll_semantics"])
            ),
        )
        for asset, spec in assets_raw.items()
        if isinstance(spec, dict)
    }
    policy = PortfolioAccountingPolicy(
        version=str(raw["version"]),
        reporting_currency=str(raw["reporting_currency"]),
        supported_currencies=tuple(str(x) for x in raw["supported_currencies"]),
        assets=assets,
        pricing_basis=str(raw.get("pricing_basis", RESEARCH_PROXY_RETURN_TIMING_BASIS)),
        performance_semantics=str(
            raw.get("performance_semantics", RESEARCH_PROXY_PERFORMANCE_SEMANTICS)
        ),
    )
    policy.validate()
    return policy


def embedded_accounting_required_series_ids(
    return_specs: Mapping[str, AssetReturnSpec],
) -> set[str]:
    """Declare FX/hedge inputs that must pass the same #18 formal query."""
    result: set[str] = set()
    for spec in return_specs.values():
        accounting = spec.accounting
        if not isinstance(accounting, Mapping):
            continue
        fx = accounting.get("fx")
        if isinstance(fx, Mapping) and fx.get("series_id"):
            result.add(str(fx["series_id"]))
        hedge_series = accounting.get("hedge_return_series_id")
        if hedge_series:
            result.add(str(hedge_series))
    return result


def embedded_accounting_disclosure(
    return_specs: Mapping[str, AssetReturnSpec],
) -> dict[str, Any] | None:
    """Expose the frozen D2 policy without recomputing return logic."""
    payloads = {
        asset: dict(spec.accounting)
        for asset, spec in return_specs.items()
        if isinstance(spec.accounting, Mapping)
    }
    if not payloads:
        return None
    if len(payloads) != len(return_specs):
        raise ValueError("accounting_policy_must_cover_all_assets")
    global_fields = (
        "policy_version",
        "reporting_currency",
        "supported_currencies",
        "pricing_basis",
        "performance_semantics",
    )
    first = next(iter(payloads.values()))
    global_values = {field: first.get(field) for field in global_fields}
    for payload in payloads.values():
        if any(payload.get(field) != global_values[field] for field in global_fields):
            raise ValueError("embedded_accounting_policy_inconsistent")
    assets = {
        asset: {key: value for key, value in payload.items() if key not in global_fields}
        for asset, payload in payloads.items()
    }
    return {**global_values, "assets": assets}


def _utc(value) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return (
        timestamp.tz_localize("UTC")
        if timestamp.tzinfo is None
        else timestamp.tz_convert("UTC")
    )


def _compatible_return_type(spec: AssetReturnSpec, accounting: AssetAccountingSpec) -> bool:
    allowed = {
        "price": {
            "PRICE_RETURN",
            "TOTAL_RETURN",
            "FUTURES_CONTINUOUS_ROLL_PROXY",
            "UNRESOLVED",
        },
        "yield_duration_proxy": {"BOND_YIELD_DURATION_PROXY"},
        "cash": {"CASH_RATE"},
    }
    return accounting.return_type in allowed.get(spec.kind, set())


def _fx_quote_at(
    observations: pd.DataFrame,
    spec: FXConversionSpec,
    boundary,
) -> tuple[float | None, dict[str, Any], str | None]:
    when = _utc(boundary)
    required = {"series_id", "observation_date", "available_at", "value"}
    if not required.issubset(observations.columns):
        return None, {}, "fx_observation_columns_missing"
    rows = observations[observations["series_id"] == spec.series_id].copy()
    if rows.empty:
        return None, {}, "fx_series_missing"
    rows["_obs_date"] = pd.to_datetime(rows["observation_date"], utc=True, errors="coerce")
    rows["_available"] = pd.to_datetime(rows["available_at"], utc=True, errors="coerce")
    rows["_value"] = pd.to_numeric(rows["value"], errors="coerce")
    rows = rows[
        rows["_obs_date"].notna()
        & rows["_available"].notna()
        & rows["_value"].notna()
        & (rows["_obs_date"].dt.date <= when.date())
        & (rows["_available"] <= when)
    ]
    if rows.empty:
        return None, {}, "fx_quote_unavailable_at_boundary"
    latest_date = rows["_obs_date"].max()
    rows = rows[rows["_obs_date"] == latest_date]
    row = rows.sort_values("_available").iloc[-1]
    if float(row["_value"]) <= 0:
        return None, {}, "fx_quote_nonpositive"
    if "quality" in row.index:
        quality = str(row["quality"]).strip().lower()
        if quality in _BLOCKED_QUALITIES:
            return None, {"quality": quality}, f"fx_quality_blocked:{quality}"
    age_hours = (when - row["_available"]).total_seconds() / 3600.0
    if age_hours > spec.max_age_hours:
        return (
            None,
            {"available_at": row["_available"], "age_hours": age_hours},
            "fx_quote_stale",
        )
    value = float(row["_value"])
    reporting_per_local = (
        value if spec.quote_direction == "reporting_per_local" else 1.0 / value
    )
    return (
        reporting_per_local,
        {
            "series_id": spec.series_id,
            "quote_direction": spec.quote_direction,
            "raw_value": value,
            "reporting_per_local": reporting_per_local,
            "observation_date": row["_obs_date"],
            "available_at": row["_available"],
            "age_hours": age_hours,
        },
        None,
    )


def portfolio_reporting_currency_return(
    observations: pd.DataFrame,
    allocation: Mapping[str, float],
    decision,
    next_decision,
    *,
    return_specs: Mapping[str, AssetReturnSpec],
    policy: PortfolioAccountingPolicy,
    pricing_start_at=None,
    pricing_end_at=None,
    fx_start_at=None,
    fx_end_at=None,
) -> ReturnAccountingResult:
    policy.validate()
    price_start = _utc(pricing_start_at if pricing_start_at is not None else decision)
    if next_decision is None:
        return ReturnAccountingResult(
            "NOT_APPLICABLE",
            policy.reporting_currency,
            None,
            {},
            {},
            {},
            (),
            price_start,
            None,
            None,
            None,
            policy.pricing_basis,
            policy.performance_semantics,
        )
    price_end = _utc(pricing_end_at if pricing_end_at is not None else next_decision)
    fx_start = _utc(fx_start_at if fx_start_at is not None else price_start)
    fx_end = _utc(fx_end_at if fx_end_at is not None else price_end)
    if fx_start != price_start or fx_end != price_end:
        return ReturnAccountingResult(
            "BLOCKED",
            policy.reporting_currency,
            None,
            {},
            {},
            {},
            ("fx_boundary_mismatch_with_asset_pricing",),
            price_start,
            price_end,
            fx_start,
            fx_end,
            policy.pricing_basis,
            policy.performance_semantics,
        )

    blockers: list[str] = []
    local_returns: dict[str, float] = {}
    reporting_returns: dict[str, float] = {}
    by_asset: dict[str, dict[str, Any]] = {}
    for asset, weight in allocation.items():
        if float(weight) == 0.0:
            continue
        return_spec = return_specs.get(asset)
        accounting = policy.assets.get(asset)
        if return_spec is None:
            blockers.append(f"{asset}:return_spec_missing")
            continue
        if accounting is None:
            blockers.append(f"{asset}:accounting_spec_missing")
            continue
        detail: dict[str, Any] = {
            "local_currency": accounting.local_currency,
            "reporting_currency": policy.reporting_currency,
            "return_type": accounting.return_type,
            "hedge_status": accounting.hedge_status,
            "fx_mapping_status": accounting.fx_mapping_status,
            "pricing_start_at": price_start,
            "pricing_end_at": price_end,
        }
        by_asset[asset] = detail
        if not _compatible_return_type(return_spec, accounting):
            blockers.append(f"{asset}:return_type_incompatible")
            detail["status"] = "BLOCKED"
            continue
        if accounting.return_type == "UNRESOLVED":
            blockers.append(f"{asset}:return_type_unresolved")
            detail["status"] = "BLOCKED"
            continue
        if accounting.return_type == "FUTURES_CONTINUOUS_ROLL_PROXY" and (
            not accounting.futures_roll_semantics
            or accounting.futures_roll_semantics.upper() == "UNVERIFIED"
        ):
            blockers.append(f"{asset}:futures_roll_semantics_unverified")
            detail["status"] = "BLOCKED"
            continue

        local_return = period_asset_return(observations, return_spec, price_start, price_end)
        if local_return is None:
            blockers.append(f"{asset}:local_return_unavailable")
            detail["status"] = "BLOCKED"
            continue
        local_return = float(local_return)
        local_returns[asset] = local_return
        detail["local_return"] = local_return

        if accounting.local_currency == policy.reporting_currency:
            reporting_return = local_return
            detail["conversion"] = "not_required"
        elif accounting.hedge_status == "HEDGED":
            if not accounting.hedge_return_series_id:
                blockers.append(f"{asset}:hedge_return_series_missing")
                detail["status"] = "BLOCKED"
                continue
            hedge_return = period_asset_return(
                observations,
                AssetReturnSpec(accounting.hedge_return_series_id, kind="price"),
                price_start,
                price_end,
            )
            if hedge_return is None:
                blockers.append(f"{asset}:hedge_return_unavailable")
                detail["status"] = "BLOCKED"
                continue
            reporting_return = (1.0 + local_return) * (1.0 + float(hedge_return)) - 1.0
            detail["conversion"] = "explicit_hedge_return_overlay"
            detail["hedge_return"] = float(hedge_return)
            detail["hedge_return_series_id"] = accounting.hedge_return_series_id
        else:
            if accounting.fx_mapping_status != "RESOLVED" or accounting.fx is None:
                blockers.append(f"{asset}:fx_mapping_unresolved")
                detail["status"] = "BLOCKED"
                continue
            start_rate, start_meta, start_error = _fx_quote_at(
                observations,
                accounting.fx,
                fx_start,
            )
            end_rate, end_meta, end_error = _fx_quote_at(
                observations,
                accounting.fx,
                fx_end,
            )
            detail["fx_start"] = start_meta
            detail["fx_end"] = end_meta
            if start_error or end_error or start_rate is None or end_rate is None:
                error = start_error or end_error or "fx_quote_unavailable"
                blockers.append(f"{asset}:{error}")
                detail["status"] = "BLOCKED"
                continue
            reporting_return = (1.0 + local_return) * (end_rate / start_rate) - 1.0
            detail["conversion"] = "unhedged_spot_fx"

        reporting_returns[asset] = float(reporting_return)
        detail["reporting_return"] = float(reporting_return)
        detail["status"] = "RESOLVED"

    if blockers:
        return ReturnAccountingResult(
            "BLOCKED",
            policy.reporting_currency,
            None,
            reporting_returns,
            local_returns,
            by_asset,
            tuple(blockers),
            price_start,
            price_end,
            fx_start,
            fx_end,
            policy.pricing_basis,
            policy.performance_semantics,
        )
    gross = sum(float(allocation[asset]) * value for asset, value in reporting_returns.items())
    return ReturnAccountingResult(
        "RESOLVED",
        policy.reporting_currency,
        float(gross),
        reporting_returns,
        local_returns,
        by_asset,
        (),
        price_start,
        price_end,
        fx_start,
        fx_end,
        policy.pricing_basis,
        policy.performance_semantics,
    )


__all__ = [
    "AssetAccountingSpec",
    "FXConversionSpec",
    "PortfolioAccountingPolicy",
    "ReturnAccountingResult",
    "embedded_accounting_disclosure",
    "embedded_accounting_required_series_ids",
    "load_return_accounting_policy",
    "portfolio_reporting_currency_return",
]
