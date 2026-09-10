"""Causal research-only transforms for Treasury / NY Fed C0 staging rows."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from cross_asset.ingestion.treasury_nyfed_pit import parse_date, visible_asof


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"null", "none", "na"}:
        return None
    return float(text.replace(",", ""))


def _series(
    rows: Iterable[dict[str, Any]],
    *,
    value_field: str,
    filter_fn=None,
) -> pd.Series:
    values: dict[pd.Timestamp, float] = {}
    for row in rows:
        if filter_fn is not None and not filter_fn(row):
            continue
        number = _number(row.get(value_field))
        if number is None:
            continue
        values[pd.Timestamp(parse_date(str(row.get("observation_date"))))] = number
    return pd.Series(values, dtype=float).sort_index()


def causal_change(series: pd.Series, *, periods: int = 1) -> pd.Series:
    return series.diff(periods=periods)


def rolling_zscore(series: pd.Series, *, window: int, min_periods: int | None = None) -> pd.Series:
    if window < 2:
        raise ValueError("rolling_zscore_window_must_be_at_least_two")
    min_periods = min_periods or window
    mean = series.rolling(window, min_periods=min_periods).mean()
    std = series.rolling(window, min_periods=min_periods).std(ddof=0)
    return (series - mean) / std.replace(0.0, np.nan)


def _last_percentile(values: np.ndarray) -> float:
    if len(values) == 0 or np.isnan(values[-1]):
        return np.nan
    valid = values[~np.isnan(values)]
    if not len(valid):
        return np.nan
    return float((valid <= values[-1]).sum() / len(valid))


def rolling_percentile(series: pd.Series, *, window: int, min_periods: int | None = None) -> pd.Series:
    if window < 2:
        raise ValueError("rolling_percentile_window_must_be_at_least_two")
    min_periods = min_periods or window
    return series.rolling(window, min_periods=min_periods).apply(_last_percentile, raw=True)


def tga_balances(rows: Iterable[dict[str, Any]]) -> pd.Series:
    return _series(
        rows,
        value_field="close_today_bal",
        filter_fn=lambda row: "Treasury General Account" in str(row.get("account_type") or ""),
    )


def onrrp_accepted(rows: Iterable[dict[str, Any]]) -> pd.Series:
    return _series(rows, value_field="totalAmtAccepted")


def soma_total(rows: Iterable[dict[str, Any]]) -> pd.Series:
    return _series(rows, value_field="total")


def dealer_positions(rows: Iterable[dict[str, Any]]) -> pd.Series:
    return _series(rows, value_field="value")


def auction_stats(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    visible = list(rows)
    if not visible:
        return {"count": 0}
    covers = [value for value in (_number(row.get("bid_to_cover_ratio")) for row in visible) if value is not None]
    tails: list[float] = []
    for row in visible:
        high = _number(row.get("high_yield"))
        avg = _number(row.get("avg_med_yield"))
        if high is not None and avg is not None:
            tails.append(high - avg)
    buckets: dict[str, int] = {}
    for row in visible:
        key = str(row.get("security_type") or "UNKNOWN")
        buckets[key] = buckets.get(key, 0) + 1
    return {
        "count": len(visible),
        "mean_bid_to_cover": float(np.mean(covers)) if covers else None,
        "mean_tail": float(np.mean(tails)) if tails else None,
        "issuance_mix": buckets,
    }


def mspd_issuance_mix(rows: Iterable[dict[str, Any]]) -> dict[str, float]:
    mix: dict[str, float] = {}
    for row in rows:
        if str(row.get("security_type_desc") or "") != "Marketable":
            continue
        klass = str(row.get("security_class_desc") or "UNKNOWN")
        amount = _number(row.get("total_mil_amt"))
        if amount is None:
            continue
        mix[klass] = mix.get(klass, 0.0) + amount
    return mix


def net_liquidity_components(
    *,
    tga: pd.Series,
    onrrp: pd.Series,
    soma: pd.Series,
) -> dict[str, Any]:
    """Research components only. Not an allocation signal."""
    aligned = pd.concat(
        [
            causal_change(tga).rename("tga_change"),
            causal_change(onrrp).rename("onrrp_change"),
            causal_change(soma).rename("soma_change"),
        ],
        axis=1,
    )
    latest = aligned.dropna(how="all").tail(1)
    payload = {
        "tga_change": None if latest.empty else _optional(latest["tga_change"].iloc[-1]),
        "onrrp_change": None if latest.empty else _optional(latest["onrrp_change"].iloc[-1]),
        "soma_change": None if latest.empty else _optional(latest["soma_change"].iloc[-1]),
        "allocation_signal": False,
    }
    if latest.empty:
        payload["net_liquidity_research_component"] = None
    else:
        payload["net_liquidity_research_component"] = _optional(
            -(latest["tga_change"].fillna(0.0) + latest["onrrp_change"].fillna(0.0)).iloc[-1]
            + latest["soma_change"].fillna(0.0).iloc[-1]
        )
    return payload


def _optional(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return float(value)


def research_components(
    rows_by_dataset: dict[str, list[dict[str, Any]]],
    decision_time: str,
) -> dict[str, Any]:
    tga_rows = visible_asof(rows_by_dataset.get("TREASURY_DTS_OPERATING_CASH") or [], decision_time)
    onrrp_rows = visible_asof(rows_by_dataset.get("NYFED_ONRRP_RESULTS") or [], decision_time)
    soma_rows = visible_asof(rows_by_dataset.get("NYFED_SOMA_SUMMARY") or [], decision_time)
    auction_rows = visible_asof(rows_by_dataset.get("TREASURY_AUCTIONS") or [], decision_time)
    pd_rows = visible_asof(rows_by_dataset.get("NYFED_PD_TREASURY_POSITIONS") or [], decision_time)
    mspd_rows = visible_asof(rows_by_dataset.get("TREASURY_MSPD_TABLE_1") or [], decision_time)

    tga = tga_balances(tga_rows)
    onrrp = onrrp_accepted(onrrp_rows)
    soma = soma_total(soma_rows)
    dealer = dealer_positions(pd_rows)

    tga_weekly = causal_change(tga, periods=min(5, max(1, len(tga) - 1))) if len(tga) > 1 else tga
    dealer_z = rolling_zscore(dealer, window=min(5, max(2, len(dealer))), min_periods=2) if len(dealer) >= 2 else dealer
    dealer_p = (
        rolling_percentile(dealer, window=min(5, max(2, len(dealer))), min_periods=2) if len(dealer) >= 2 else dealer
    )
    return {
        "tga_daily_change": None
        if tga.empty
        else _optional(causal_change(tga).dropna().iloc[-1] if len(tga) > 1 else None),
        "tga_weekly_change": None
        if tga_weekly.empty
        else _optional(tga_weekly.dropna().iloc[-1] if len(tga_weekly.dropna()) else None),
        "onrrp_change": None
        if onrrp.empty
        else _optional(causal_change(onrrp).dropna().iloc[-1] if len(onrrp) > 1 else None),
        "soma_composition_change": None
        if soma.empty
        else _optional(causal_change(soma).dropna().iloc[-1] if len(soma) > 1 else None),
        "auction": auction_stats(auction_rows),
        "mspd_marketable_mix": mspd_issuance_mix(mspd_rows),
        "dealer_inventory_zscore": None
        if dealer_z.empty
        else _optional(dealer_z.dropna().iloc[-1] if len(dealer_z.dropna()) else None),
        "dealer_inventory_percentile": None
        if dealer_p.empty
        else _optional(dealer_p.dropna().iloc[-1] if len(dealer_p.dropna()) else None),
        "net_liquidity": net_liquidity_components(tga=tga, onrrp=onrrp, soma=soma),
        "as_of_dates": {
            "tga_last": None if tga.empty else str(tga.index[-1].date()),
            "onrrp_last": None if onrrp.empty else str(onrrp.index[-1].date()),
            "soma_last": None if soma.empty else str(soma.index[-1].date()),
        },
        "lookback_note": "Transforms use only rows with available_at <= decision_time.",
    }


def observation_window(start: date, end: date) -> tuple[date, date]:
    return start, end
