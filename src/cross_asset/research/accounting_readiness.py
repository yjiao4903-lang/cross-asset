"""Fail-closed semantic checks for embedded formal return accounting.

This module does not resolve source truth or compute returns. It validates the
accounting disclosure already embedded in ``AssetReturnSpec`` so formal
readiness can expose the same unresolved economic contracts before execution.
"""

from __future__ import annotations

from collections.abc import Mapping

from cross_asset.backtest.accounting import embedded_accounting_disclosure
from cross_asset.backtest.returns import AssetReturnSpec

_ALLOWED_RETURN_TYPES_BY_KIND = {
    "price": {"PRICE_RETURN", "TOTAL_RETURN", "FUTURES_CONTINUOUS_ROLL_PROXY"},
    "yield_duration_proxy": {"BOND_YIELD_DURATION_PROXY"},
    "cash": {"CASH_RATE"},
}
_VALID_HEDGE_STATUS = {"UNHEDGED", "HEDGED"}
_VALID_FX_STATUS = {"NOT_REQUIRED", "RESOLVED", "UNRESOLVED"}
_VALID_FX_DIRECTIONS = {"reporting_per_local", "local_per_reporting"}


def _text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def accounting_semantic_blockers(
    return_specs: Mapping[str, AssetReturnSpec],
) -> tuple[str, ...]:
    """Return deterministic blockers for unresolved embedded accounting policy.

    The gate deliberately validates declarations only. It never infers a source,
    FX pair, return type, roll convention, or missing value.
    """

    if not return_specs:
        return ("accounting:policy:missing",)

    try:
        disclosure = embedded_accounting_disclosure(return_specs)
    except ValueError as exc:
        return (f"accounting:policy:{exc}",)
    if disclosure is None:
        return ("accounting:policy:missing",)

    blockers: set[str] = set()
    reporting_currency = _text(disclosure.get("reporting_currency"))
    supported_raw = disclosure.get("supported_currencies")
    if not reporting_currency:
        blockers.add("accounting:policy:reporting_currency_missing")
    if not isinstance(supported_raw, (list, tuple, set)) or not supported_raw:
        supported: set[str] = set()
        blockers.add("accounting:policy:supported_currencies_missing")
    else:
        supported = {_text(value) for value in supported_raw}
        supported.discard(None)
        if reporting_currency and reporting_currency not in supported:
            blockers.add("accounting:policy:reporting_currency_not_supported")

    for asset, return_spec in sorted(return_specs.items()):
        accounting = return_spec.accounting
        if not isinstance(accounting, Mapping):
            blockers.add(f"accounting:{asset}:accounting_spec_missing")
            continue

        local_currency = _text(accounting.get("local_currency"))
        return_type = _text(accounting.get("return_type"))
        hedge_status = _text(accounting.get("hedge_status"))
        fx_status = _text(accounting.get("fx_mapping_status"))
        fx = accounting.get("fx")

        if not local_currency:
            blockers.add(f"accounting:{asset}:local_currency_missing")
        elif supported and local_currency not in supported:
            blockers.add(f"accounting:{asset}:unsupported_asset_currency:{local_currency}")

        if not return_type or return_type == "UNRESOLVED":
            blockers.add(f"accounting:{asset}:return_type_unresolved")
        elif return_type not in _ALLOWED_RETURN_TYPES_BY_KIND.get(return_spec.kind, set()):
            blockers.add(f"accounting:{asset}:return_type_incompatible")

        if return_type == "FUTURES_CONTINUOUS_ROLL_PROXY":
            roll = _text(accounting.get("futures_roll_semantics"))
            if not roll or roll.upper() == "UNVERIFIED":
                blockers.add(f"accounting:{asset}:futures_roll_semantics_unverified")

        if hedge_status not in _VALID_HEDGE_STATUS:
            blockers.add(f"accounting:{asset}:hedge_status_invalid")
        if fx_status not in _VALID_FX_STATUS:
            blockers.add(f"accounting:{asset}:fx_mapping_status_invalid")

        if not reporting_currency or not local_currency:
            continue
        if local_currency == reporting_currency:
            if fx_status != "NOT_REQUIRED" or fx is not None:
                blockers.add(
                    f"accounting:{asset}:same_currency_fx_mapping_must_be_not_required"
                )
            continue

        if hedge_status == "HEDGED":
            if not _text(accounting.get("hedge_return_series_id")):
                blockers.add(f"accounting:{asset}:hedge_return_series_missing")
            continue
        if hedge_status != "UNHEDGED":
            continue

        if fx_status != "RESOLVED":
            blockers.add(f"accounting:{asset}:fx_mapping_unresolved")
            continue
        if not isinstance(fx, Mapping) or not _text(fx.get("series_id")):
            blockers.add(f"accounting:{asset}:fx_contract_missing")
            continue

        fx_local = _text(fx.get("local_currency"))
        fx_reporting = _text(fx.get("reporting_currency"))
        if fx_local != local_currency or fx_reporting != reporting_currency:
            blockers.add(f"accounting:{asset}:fx_currency_pair_mismatch")
        if _text(fx.get("quote_direction")) not in _VALID_FX_DIRECTIONS:
            blockers.add(f"accounting:{asset}:fx_quote_direction_invalid")
        try:
            max_age_hours = float(fx.get("max_age_hours"))
        except (TypeError, ValueError):
            max_age_hours = 0.0
        if max_age_hours <= 0:
            blockers.add(f"accounting:{asset}:fx_max_age_hours_must_be_positive")

    return tuple(sorted(blockers))


__all__ = ["accounting_semantic_blockers"]
