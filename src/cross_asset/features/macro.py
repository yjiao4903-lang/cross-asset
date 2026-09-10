"""Point-in-time-safe transforms for macro observations."""

from __future__ import annotations

from dataclasses import dataclass
from math import isnan

import pandas as pd


@dataclass(frozen=True)
class TransformResult:
    value: float | None
    available: bool
    reason: str | None = None


@dataclass(frozen=True)
class TransformUnitSemantics:
    """Explicit raw and pre-normalization units for one macro transform."""

    transform_type: str
    raw_unit: str | None
    derived_unit: str | None
    resolved: bool
    reason: str | None = None


def transform_unit_semantics(definition: dict | None) -> TransformUnitSemantics:
    """Read explicit unit metadata without inferring unresolved source truth."""

    cfg = definition or {}
    transform = cfg.get("transform", {}) or {}
    transform_type = str(transform.get("type", "level"))
    raw_unit = cfg.get("raw_unit")
    derived_unit = cfg.get("derived_unit")
    unresolved = {None, "", "TBD", "UNRESOLVED"}
    if transform_type == "ambiguous_raw_semantics":
        return TransformUnitSemantics(
            transform_type,
            raw_unit,
            derived_unit,
            False,
            "ambiguous_raw_semantics",
        )
    if raw_unit in unresolved or derived_unit in unresolved:
        return TransformUnitSemantics(
            transform_type,
            raw_unit,
            derived_unit,
            False,
            "unit_semantics_unresolved",
        )
    return TransformUnitSemantics(
        transform_type,
        str(raw_unit),
        str(derived_unit),
        True,
    )


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key)


def _ordered_rows(series):
    if hasattr(series, "sort_values"):
        return list(series.sort_values("observation_date").to_dict("records"))
    rows = list(series)
    if not rows or all(_get(row, "observation_date") is None for row in rows):
        return rows
    return sorted(
        rows,
        key=lambda row: (
            _get(row, "observation_date") is None,
            _get(row, "observation_date"),
        ),
    )


def _values(series):
    if hasattr(series, "sort_values"):
        return list(series.sort_values("observation_date")["value"])
    return [_get(x, "value") for x in _ordered_rows(series)]


def _date_key(value):
    """Return a comparable calendar date while preserving missingness."""
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).normalize()


def _dated_value_map(rows, period="date"):
    def key(value):
        stamp = _date_key(value)
        if stamp is None:
            return None
        if period == "month":
            return stamp.year * 12 + stamp.month
        if period == "quarter":
            return stamp.year * 4 + (stamp.quarter - 1)
        return stamp

    return {
        key(_get(row, "observation_date")): _get(row, "value")
        for row in rows
        if key(_get(row, "observation_date")) is not None
    }


def _period_lag(rows, months, period="date"):
    """Find an exact date/month/quarter lag; never substitute by row position."""
    ordered = _ordered_rows(rows)
    # The last observation period is the decision point. Do not walk backward
    # over a missing current value, otherwise a stale period is silently used.
    current = ordered[-1] if ordered else None
    if current is None:
        return None, None
    current_date = _date_key(_get(current, "observation_date"))
    if current_date is None:
        return current, None
    if period == "month":
        target = current_date.year * 12 + current_date.month - months
    elif period == "quarter":
        if months % 3:
            raise ValueError("quarter lag_months must be divisible by three")
        target = current_date.year * 4 + (current_date.quarter - 1) - months // 3
    else:
        target = current_date - pd.DateOffset(months=months)
    previous = _dated_value_map(ordered, period).get(target)
    return current, previous


def transform_series(series, transform=None):
    """Transform an ordered level series without imputing missing values."""

    cfg = transform or {}
    typ = cfg.get("type", "level")
    if typ == "ambiguous_raw_semantics":
        return TransformResult(None, False, "ambiguous_raw_semantics")
    rows = _ordered_rows(series)
    vals = [_get(row, "value") for row in rows]
    vals = [None if v is None else float(v) for v in vals]
    valid = [v for v in vals if v is not None]
    if not valid:
        return TransformResult(None, False, "missing")
    if typ == "level":
        out = valid[-1] - float(cfg.get("baseline", 0))
    elif typ in ("diff", "mom"):
        # Adjacent observations are intentional for daily/weekly series. A
        # missing adjacent value remains unavailable; it is never filtered out.
        current = vals[-1]
        previous = vals[-2] if len(vals) >= 2 else None
        out = current - previous if current is not None and previous is not None else float("nan")
    elif typ in ("yoy", "difference_12m", "pct_change_12m", "change_in_yoy_pp"):
        months = int(cfg.get("lag_months", 12))
        current_row, previous = _period_lag(rows, months, cfg.get("period", "date"))
        current = _get(current_row, "value") if current_row is not None else None
        if current is None or previous is None:
            return TransformResult(None, False, "missing_lag_period")
        if typ == "pct_change_12m" or typ == "yoy":
            out = (float(current) / float(previous) - 1.0) * 100.0 if previous else float("nan")
        else:
            out = float(current) - float(previous)
    elif typ == "zscore":
        if len(valid) < 2:
            return TransformResult(None, False, "insufficient_history")
        avg = sum(valid) / len(valid)
        sd = (sum((x - avg) ** 2 for x in valid) / len(valid)) ** 0.5
        if not sd:
            return TransformResult(None, False, "zero_variance_continuation")
        out = (valid[-1] - avg) / sd
    else:
        raise ValueError(f"unsupported macro transform: {typ}")
    if isnan(out):
        return TransformResult(None, False, "insufficient_history")
    if cfg.get("direction") == "negative":
        out = -out
    return TransformResult(out, True)


def transform_history(series, transform=None) -> pd.Series:
    """Return the causal transformed history for an already deduplicated vintage snapshot."""

    rows = _ordered_rows(series)
    values = []
    index = []
    for end in range(1, len(rows) + 1):
        result = transform_series(rows[:end], transform)
        values.append(result.value if result.available else None)
        index.append(_get(rows[end - 1], "observation_date"))
    return pd.Series(values, index=pd.to_datetime(index), dtype=float)


def macro_transform(series, transform=None):
    return transform_series(series, transform)


__all__ = [
    "TransformResult",
    "TransformUnitSemantics",
    "macro_transform",
    "transform_history",
    "transform_series",
    "transform_unit_semantics",
]
