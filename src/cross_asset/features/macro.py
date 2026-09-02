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


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key)


def _ordered_rows(series):
    if hasattr(series, "sort_values"):
        return list(series.sort_values("observation_date").to_dict("records"))
    return sorted(series, key=lambda row: _get(row, "observation_date"))


def _values(series):
    if hasattr(series, "sort_values"):
        return list(series.sort_values("observation_date")["value"])
    return [_get(x, "value") for x in _ordered_rows(series)]


def transform_series(series, transform=None):
    """Transform an ordered level series without imputing missing values."""

    cfg = transform or {}
    typ = cfg.get("type", "level")
    vals = _values(series)
    vals = [None if v is None else float(v) for v in vals]
    valid = [v for v in vals if v is not None]
    if not valid:
        return TransformResult(None, False, "missing")
    if typ == "level":
        out = valid[-1] - float(cfg.get("baseline", 0))
    elif typ in ("diff", "mom"):
        out = valid[-1] - (
            valid[-2] if len(valid) >= 2 and valid[-2] is not None else float("nan")
        )
    elif typ == "yoy":
        out = valid[-1] - (valid[-13] if len(valid) >= 13 else float("nan"))
    elif typ == "zscore":
        if len(valid) < 2:
            return TransformResult(None, False, "insufficient_history")
        avg = sum(valid) / len(valid)
        sd = (sum((x - avg) ** 2 for x in valid) / len(valid)) ** 0.5
        out = (valid[-1] - avg) / sd if sd else 0.0
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


__all__ = ["TransformResult", "macro_transform", "transform_history", "transform_series"]
